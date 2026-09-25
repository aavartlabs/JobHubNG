"""The pi05 job warehouse: every job EverJobs returns, stored once.

Replaces "filter the sweep, write a dump, keep it forever": each sweep is upserted here
unfiltered, so the serving DB (pi09) can be fed any slice of it later, and nothing
filtered out today is lost for good.

A job is the same job if it has the same EverJobs id, or else the same fingerprint
(normalised title + company + city) -- which folds the same opening listed on two sites
into one row. Posted-date freshness is enforced on every sighting: a job older than
max_posted_age_days is neither inserted nor touched, so retention (by last_seen) retires
it even while the source keeps listing it.

Nothing is lost: a content change first copies the previous version into job_versions,
and retention moves retired jobs into jobs_archive instead of deleting them.
"""
import hashlib
import json
import re
import sqlite3
import sys
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

# poc/ on the path, for jobhub_poc.dates (standard library only). On pi05 the shared
# files are deployed alongside scraper/ (see CLAUDE.md's pi05 deployment notes).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobhub_poc.dates import normalize_posted  # noqa: E402
from jobhub_poc.job_links import human_url  # noqa: E402

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
    raw_json          TEXT NOT NULL,
    content_hash      TEXT
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
    skipped       INTEGER NOT NULL,
    unchanged     INTEGER NOT NULL DEFAULT 0
);

-- What enrich.py fetched to fill a gap in EverJobs' record (today: SmartRecruiters jobs,
-- which arrive with no description and an API URL as their link). Kept apart from jobs and
-- laid over each sighting by ingest() *before* hashing, so the next sweep's bare record
-- doesn't count as a change. status: ok | gone (posting removed) | error (retry later).
CREATE TABLE IF NOT EXISTS enrichments (
    source_id    TEXT PRIMARY KEY,
    source       TEXT NOT NULL,
    status       TEXT NOT NULL,
    description  TEXT,
    apply_url    TEXT,
    error        TEXT,
    fetched_at   TEXT NOT NULL
);
"""

# Every column of a jobs row, in order -- jobs_archive keeps the same set (plus job_id and
# archived_at), and purge_warehouse copies them by this list.
JOB_COLUMNS = (
    "source_id", "fingerprint", "site", "title", "company_name", "location", "description",
    "employment_type", "is_remote", "apply_url", "posted_at_source", "posted_at",
    "first_seen_at", "last_seen_at", "updated_at", "raw_json", "content_hash",
)

# History (2026-09-24): nothing is overwritten or deleted outright.
#  - job_versions: a job's previous content, zlib-compressed raw JSON, and the span it was
#    current [valid_from, valid_to). One row per real content change.
#  - jobs_archive: jobs retired by retention, with everything they had.
_HISTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS job_versions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id        INTEGER NOT NULL,
    content_hash  TEXT,
    raw_json_z    BLOB NOT NULL,
    valid_from    TEXT NOT NULL,
    valid_to      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wh_job_versions_job ON job_versions(job_id);

CREATE TABLE IF NOT EXISTS jobs_archive (
    archive_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id        INTEGER NOT NULL,
""" + ",\n".join(f"    {c} {'INTEGER' if c == 'is_remote' else 'TEXT'}" for c in JOB_COLUMNS) + """,
    archived_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wh_jobs_archive_source ON jobs_archive(source_id);
"""

# Columns added after the first pi05 dry run (2026-09-23); open_warehouse adds them to an
# older file in place.
_ADDED_COLUMNS = {"jobs": {"content_hash": "TEXT"}, "ingest_runs": {"unchanged": "INTEGER NOT NULL DEFAULT 0"}}

_NON_WORD = re.compile(r"[^a-z0-9]+")


def open_warehouse(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(_SCHEMA)
    conn.executescript(_HISTORY_SCHEMA)
    for table, columns in _ADDED_COLUMNS.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, decl in columns.items():
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
    conn.commit()
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
        "apply_url": human_url(job.get("applyUrl") or job.get("jobUrl")),
        "posted_at_source": None if job.get("datePosted") is None else str(job.get("datePosted")),
        "posted_at": posted_at,
        "raw_json": json.dumps(job, separators=(",", ":")),
    }


def load_version(raw_json_z):
    """The job JSON stored in a job_versions row."""
    return json.loads(zlib.decompress(raw_json_z))


def _save_version(conn, job_id, now_stamp):
    old = conn.execute("SELECT raw_json, content_hash, updated_at FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.execute(
        "INSERT INTO job_versions (job_id, content_hash, raw_json_z, valid_from, valid_to) VALUES (?, ?, ?, ?, ?)",
        (job_id, old["content_hash"], zlib.compress(old["raw_json"].encode(), 9), old["updated_at"], now_stamp),
    )


def overlay(conn, job):
    """`job` with what enrich.py found filled in -- only where EverJobs left a gap (no
    description), so a record that later arrives complete wins. Same job back if nothing
    applies. The result is stable for a given enrichment, which keeps content_hash stable."""
    if job.get("description") or job.get("id") is None:
        return job
    found = conn.execute("SELECT source, description, apply_url FROM enrichments "
                         "WHERE source_id = ? AND status = 'ok'", (str(job["id"]),)).fetchone()
    if found is None or not found["description"]:
        return job
    return {**job, "description": found["description"], "applyUrl": found["apply_url"] or job.get("applyUrl"),
            "_enriched": found["source"]}


def refresh_enriched(conn, job_id, now=None):
    """Apply a new enrichment to the stored job (jobs.id) now -- a normal content change:
    the old version goes to job_versions and updated_at moves, so export.py sends it in
    full. True if the row changed. Doesn't commit."""
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        return False
    job = json.loads(row["raw_json"])
    enriched = overlay(conn, job)
    if enriched is job:
        return False
    fields = _fields(enriched, row["posted_at"])
    content_hash = _content_hash(fields)
    if content_hash == row["content_hash"]:
        return False
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    _save_version(conn, row["id"], stamp)
    conn.execute(f"UPDATE jobs SET {', '.join(f'{k} = ?' for k in fields)}, updated_at = ?, content_hash = ? WHERE id = ?",
                 (*fields.values(), stamp, content_hash, row["id"]))
    return True


def _content_hash(fields):
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def ingest(conn, jobs, max_posted_age_days, now=None):
    """Upserts one sweep. Returns counts: fetched/inserted/updated (content changed)/
    unchanged (only seen again)/duplicates/rejected_old/skipped.

    updated_at moves only when a job's content changes; last_seen_at moves on every
    sighting. export.py relies on that to send full records only for changed jobs."""
    now = now or datetime.now(timezone.utc)
    stamp = now.isoformat()
    oldest_allowed = now - timedelta(days=max_posted_age_days) if max_posted_age_days else None
    stats = dict(fetched=len(jobs), inserted=0, updated=0, unchanged=0, duplicates=0, rejected_old=0, skipped=0)
    touched = set()

    with conn:
        for job in jobs:
            if not isinstance(job, dict) or not (job.get("title") or "").strip():
                stats["skipped"] += 1
                continue
            job = overlay(conn, job)
            fp = fingerprint(job)
            source_id = None if job.get("id") is None else str(job["id"])
            row = None
            if source_id:
                row = conn.execute("SELECT id, first_seen_at, fingerprint, content_hash FROM jobs WHERE source_id = ?",
                                   (source_id,)).fetchone()
            if row is None:
                row = conn.execute("SELECT id, first_seen_at, fingerprint, content_hash FROM jobs WHERE fingerprint = ?",
                                   (fp,)).fetchone()

            posted_at = normalize_posted(job.get("datePosted"), row["first_seen_at"] if row else now)
            if oldest_allowed and posted_at and datetime.fromisoformat(posted_at) < oldest_allowed:
                stats["rejected_old"] += 1
                continue

            if row is not None and row["id"] in touched:
                stats["duplicates"] += 1
                continue

            fields = _fields(job, posted_at)
            content_hash = _content_hash(fields)
            if row is None:
                cur = conn.execute(
                    f"""INSERT INTO jobs (source_id, fingerprint, {", ".join(fields)},
                                          first_seen_at, last_seen_at, updated_at, content_hash)
                        VALUES (?, ?, {", ".join("?" * len(fields))}, ?, ?, ?, ?)""",
                    (source_id, fp, *fields.values(), stamp, stamp, stamp, content_hash),
                )
                touched.add(cur.lastrowid)
                stats["inserted"] += 1
                continue

            if row["content_hash"] == content_hash:
                conn.execute("UPDATE jobs SET last_seen_at = ? WHERE id = ?", (stamp, row["id"]))
                touched.add(row["id"])
                stats["unchanged"] += 1
                continue

            _save_version(conn, row["id"], stamp)
            # A changed title on a known id moves its fingerprint -- unless another row
            # already owns that fingerprint, in which case the old one is kept.
            new_fp = fp if fp != row["fingerprint"] and not conn.execute(
                "SELECT 1 FROM jobs WHERE fingerprint = ?", (fp,)).fetchone() else row["fingerprint"]
            conn.execute(
                f"""UPDATE jobs SET fingerprint = ?, {", ".join(f"{k} = ?" for k in fields)},
                                    last_seen_at = ?, updated_at = ?, content_hash = ? WHERE id = ?""",
                (new_fp, *fields.values(), stamp, stamp, content_hash, row["id"]),
            )
            touched.add(row["id"])
            stats["updated"] += 1

        conn.execute(
            """INSERT INTO ingest_runs (started_at, fetched, inserted, updated, unchanged, duplicates,
                                        rejected_old, skipped)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (stamp, *(stats[k] for k in ("fetched", "inserted", "updated", "unchanged", "duplicates",
                                         "rejected_old", "skipped"))),
        )
    return stats


def purge_warehouse(conn, retention_days, now=None):
    """Retires jobs no sweep has listed for retention_days ([retention]
    warehouse_retention_days): each moves to jobs_archive with everything it had, then
    leaves jobs. Returns how many were archived."""
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=retention_days)).isoformat()
    columns = ", ".join(JOB_COLUMNS)
    with conn:
        conn.execute(
            f"""INSERT INTO jobs_archive (job_id, {columns}, archived_at)
                SELECT id, {columns}, ? FROM jobs WHERE last_seen_at < ?""",
            (now.isoformat(), cutoff),
        )
        cur = conn.execute("DELETE FROM jobs WHERE last_seen_at < ?", (cutoff,))
    return cur.rowcount
