"""The pi05 job warehouse: every job EverJobs returns, stored once.

Replaces "filter the sweep, write a dump, keep it forever": each sweep is upserted here
unfiltered, so the serving DB (pi09) can be fed any slice of it later, and nothing
filtered out today is lost for good.

A job is the same job if it has the same EverJobs id, or else the same fingerprint
(normalised title + company + city) -- which folds the same opening listed on two sites
into one row. Posted-date freshness is enforced on every sighting: a job older than
max_posted_age_days is neither inserted nor touched, so retention (by last_seen) removes
it even while the source keeps listing it.
"""
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# poc/ on the path, for jobhub_poc.dates (standard library only). On pi05 the shared
# files are deployed alongside scraper/ (see CLAUDE.md's pi05 deployment notes).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobhub_poc.dates import normalize_posted  # noqa: E402

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id         TEXT,
    fingerprint       TEXT NOT NULL UNIQUE,
    site              TEXT,
    title             TEXT NOT NULL,
    company_name      TEXT,
    location          TEXT,
    description       TEXT,
    employment_type   TEXT,
    is_remote         INTEGER NOT NULL DEFAULT 0,
    apply_url         TEXT,
    posted_at_source  TEXT,
    posted_at         TEXT,
    first_seen_at     TEXT NOT NULL,
    last_seen_at      TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    raw_json          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wh_jobs_source_id  ON jobs(source_id);
CREATE INDEX IF NOT EXISTS idx_wh_jobs_updated_at ON jobs(updated_at);
CREATE INDEX IF NOT EXISTS idx_wh_jobs_last_seen  ON jobs(last_seen_at);

CREATE TABLE IF NOT EXISTS ingest_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    TEXT NOT NULL,
    fetched       INTEGER NOT NULL,
    inserted      INTEGER NOT NULL,
    updated       INTEGER NOT NULL,
    duplicates    INTEGER NOT NULL,
    rejected_old  INTEGER NOT NULL,
    skipped       INTEGER NOT NULL
);
"""

_NON_WORD = re.compile(r"[^a-z0-9]+")


def open_warehouse(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(_SCHEMA)
    return conn


def _norm(value):
    return _NON_WORD.sub(" ", str(value or "").lower()).strip()


def _city(job):
    location = job.get("location")
    return location.get("city") if isinstance(location, dict) else None


def fingerprint(job):
    key = "|".join(_norm(v) for v in (job.get("title"), job.get("companyName"), _city(job)))
    return hashlib.sha256(key.encode()).hexdigest()


def _location_text(job):
    location = job.get("location")
    if not isinstance(location, dict):
        return None
    parts = [location.get(k) for k in ("city", "state", "country")]
    return ", ".join(p for p in parts if p) or None


def _fields(job, posted_at):
    return {
        "site": job.get("site"),
        "title": job["title"],
        "company_name": job.get("companyName"),
        "location": _location_text(job),
        "description": job.get("description"),
        "employment_type": job.get("employmentType"),
        "is_remote": 1 if job.get("isRemote") else 0,
        "apply_url": job.get("applyUrl") or job.get("jobUrl"),
        "posted_at_source": None if job.get("datePosted") is None else str(job.get("datePosted")),
        "posted_at": posted_at,
        "raw_json": json.dumps(job, separators=(",", ":")),
    }


def ingest(conn, jobs, max_posted_age_days, now=None):
    """Upserts one sweep. Returns counts: fetched/inserted/updated/duplicates/
    rejected_old/skipped."""
    now = now or datetime.now(timezone.utc)
    stamp = now.isoformat()
    oldest_allowed = now - timedelta(days=max_posted_age_days) if max_posted_age_days else None
    stats = dict(fetched=len(jobs), inserted=0, updated=0, duplicates=0, rejected_old=0, skipped=0)
    touched = set()

    with conn:
        for job in jobs:
            if not isinstance(job, dict) or not (job.get("title") or "").strip():
                stats["skipped"] += 1
                continue
            fp = fingerprint(job)
            source_id = None if job.get("id") is None else str(job["id"])
            row = None
            if source_id:
                row = conn.execute("SELECT id, first_seen_at, fingerprint FROM jobs WHERE source_id = ?",
                                   (source_id,)).fetchone()
            if row is None:
                row = conn.execute("SELECT id, first_seen_at, fingerprint FROM jobs WHERE fingerprint = ?",
                                   (fp,)).fetchone()

            posted_at = normalize_posted(job.get("datePosted"), row["first_seen_at"] if row else now)
            if oldest_allowed and posted_at and datetime.fromisoformat(posted_at) < oldest_allowed:
                stats["rejected_old"] += 1
                continue

            if row is not None and row["id"] in touched:
                stats["duplicates"] += 1
                continue

            fields = _fields(job, posted_at)
            if row is None:
                cur = conn.execute(
                    f"""INSERT INTO jobs (source_id, fingerprint, {", ".join(fields)},
                                          first_seen_at, last_seen_at, updated_at)
                        VALUES (?, ?, {", ".join("?" * len(fields))}, ?, ?, ?)""",
                    (source_id, fp, *fields.values(), stamp, stamp, stamp),
                )
                touched.add(cur.lastrowid)
                stats["inserted"] += 1
                continue

            # A changed title on a known id moves its fingerprint -- unless another row
            # already owns that fingerprint, in which case the old one is kept.
            new_fp = fp if fp != row["fingerprint"] and not conn.execute(
                "SELECT 1 FROM jobs WHERE fingerprint = ?", (fp,)).fetchone() else row["fingerprint"]
            conn.execute(
                f"""UPDATE jobs SET fingerprint = ?, {", ".join(f"{k} = ?" for k in fields)},
                                    last_seen_at = ?, updated_at = ? WHERE id = ?""",
                (new_fp, *fields.values(), stamp, stamp, row["id"]),
            )
            touched.add(row["id"])
            stats["updated"] += 1

        conn.execute(
            """INSERT INTO ingest_runs (started_at, fetched, inserted, updated, duplicates, rejected_old, skipped)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (stamp, *(stats[k] for k in ("fetched", "inserted", "updated", "duplicates", "rejected_old", "skipped"))),
        )
    return stats
