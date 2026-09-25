"""Queue a reading (job_reading.py) for every listed job that doesn't have one: after each
pipeline load (new and changed jobs; a changed description drops the old reading), and as
the one-off backfill. Background priority 0, so people's own requests (1, 5, 8, 10) go first.
Already-queued jobs aren't queued twice (tasks.enqueue).

    python -m jobhub_poc.ai.queue_reads [--limit N]
"""
import argparse

from jobhub_poc import db
from jobhub_poc.ai import tasks

MIN_DESCRIPTION = 100  # shorter postings are read without AI (worker.extract_job)


def unread(conn, limit=None):
    sql = ("SELECT j.dedupe_key FROM jobs j LEFT JOIN job_requirements r ON r.job_dedupe_key = j.dedupe_key "
           "WHERE r.job_dedupe_key IS NULL AND LENGTH(COALESCE(j.description, '')) >= ? ORDER BY j.last_seen_at DESC")
    return [r[0] for r in conn.execute(sql + (" LIMIT ?" if limit else ""), (MIN_DESCRIPTION, limit) if limit else (MIN_DESCRIPTION,))]


def queue(conn, limit=None):
    keys = unread(conn, limit)
    for key in keys:
        tasks.enqueue(conn, "extract_job", ref=key, priority=0)
    return len(keys)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    conn = db.get_connection()
    db.init_db(conn)
    print(f"queued {queue(conn, args.limit)} job reading(s)")
    conn.close()


if __name__ == "__main__":
    main()
