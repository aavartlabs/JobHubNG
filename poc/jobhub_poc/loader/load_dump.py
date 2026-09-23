"""Load an EverJobs-shaped JSON dump into the jobs table.

Real EverJobs responses (confirmed live against pi05, 2026-09-16) return
{"jobs": [...]}; each job reliably has id/site/title/companyName, but every
other field is opportunistic -- location is a nested {city,state,country}
object (often missing pieces), description can be null, and the apply link
comes back as either applyUrl or jobUrl depending on the source ATS.
"""
import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from jobhub_poc.dates import normalize_posted


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _flatten_location(location) -> str | None:
    if not isinstance(location, dict):
        return None
    parts = [location.get("city"), location.get("state"), location.get("country")]
    parts = [p for p in parts if p]
    return ", ".join(parts) if parts else None


def _dedupe_key(job: dict) -> str:
    external_id = job.get("id")
    if external_id:
        return str(external_id)
    basis = "|".join([
        str(job.get("site") or ""),
        str(job.get("title") or ""),
        str(job.get("companyName") or ""),
        str(job.get("location") or ""),
    ])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def upsert_job(conn: sqlite3.Connection, job: dict, dedupe_key: str, first_seen_at: str,
               last_seen_at: str, search_term: str | None = None) -> int | None:
    """Insert or refresh one EverJobs-shaped job keyed by dedupe_key. Returns the new
    jobs.id if it was inserted, None if an existing row was updated. Doesn't commit.
    Shared by load_dump (old dump files) and load_delta (pi05 warehouse deltas)."""
    existing = conn.execute("SELECT id, first_seen_at FROM jobs WHERE dedupe_key = ?", (dedupe_key,)).fetchone()
    apply_url = job.get("applyUrl") or job.get("jobUrl")
    posted_at = normalize_posted(job.get("datePosted"), existing[1] if existing else first_seen_at)

    if existing is None:
        cur = conn.execute(
            """
            INSERT INTO jobs (
                dedupe_key, external_job_id, source_site, search_term,
                title, company_name, location, description, employment_type,
                is_remote, apply_url, posted_at_source, posted_at,
                first_seen_at, last_seen_at, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dedupe_key,
                job.get("id"),
                job.get("site") or "everjobs",
                search_term,
                job.get("title") or "",
                job.get("companyName"),
                _flatten_location(job.get("location")),
                job.get("description"),
                job.get("employmentType"),
                1 if job.get("isRemote") else 0,
                apply_url,
                job.get("datePosted"),
                posted_at,
                first_seen_at,
                last_seen_at,
                json.dumps(job),
            ),
        )
        return cur.lastrowid

    conn.execute(
        """
        UPDATE jobs SET
            title = ?, company_name = ?, location = ?, description = ?,
            employment_type = ?, is_remote = ?, apply_url = ?,
            posted_at_source = ?, posted_at = ?, last_seen_at = ?, raw_json = ?
        WHERE dedupe_key = ?
        """,
        (
            job.get("title") or "",
            job.get("companyName"),
            _flatten_location(job.get("location")),
            job.get("description"),
            job.get("employmentType"),
            1 if job.get("isRemote") else 0,
            apply_url,
            job.get("datePosted"),
            posted_at,
            last_seen_at,
            json.dumps(job),
            dedupe_key,
        ),
    )
    return None


def load_dump(conn: sqlite3.Connection, dump_path) -> list[int]:
    """Upsert every job in dump_path's {"jobs": [...]} into the jobs table.

    Returns the list of jobs table ids that were genuinely inserted (not
    merely updated) by this call.
    """
    data = json.loads(Path(dump_path).read_text())
    now = _now_iso()
    new_ids: list[int] = []
    for job in data.get("jobs", []):
        inserted = upsert_job(conn, job, _dedupe_key(job), now, now, job.get("_search_term"))
        if inserted is not None:
            new_ids.append(inserted)
    conn.commit()
    return new_ids


def main() -> None:
    from jobhub_poc import db

    parser = argparse.ArgumentParser()
    parser.add_argument("dump_path")
    parser.add_argument("--new-ids-out", default=None)
    args = parser.parse_args()

    conn = db.get_connection()
    db.init_db(conn)
    new_ids = load_dump(conn, args.dump_path)
    conn.close()

    print(f"loaded dump, {len(new_ids)} new job(s) inserted")
    if args.new_ids_out:
        Path(args.new_ids_out).write_text(json.dumps(new_ids))


if __name__ == "__main__":
    main()
