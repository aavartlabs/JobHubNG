"""Queue a reading (job_reading.py) for every listed job that doesn't have one: after each
pipeline load (new and changed jobs; a changed description drops the old reading), and as
the one-off backfill. Background priority 0, so people's own requests (1, 5, 8, 10) go first.
Already-queued jobs aren't queued twice (tasks.enqueue).

    python -m jobhub_poc.ai.queue_reads [--limit N] [--reread-old]

--reread-old also queues jobs read before Jev (a model label not starting "jev"): the
readings stay in place until the new ones replace them.
"""
import argparse

from jobhub_poc import db
from jobhub_poc.ai import tasks

MIN_DESCRIPTION = 100  # shorter postings are read without AI (worker.extract_job)


def unread(conn, limit=None, reread_old=False):
    missing = "r.job_dedupe_key IS NULL" + (" OR r.model NOT LIKE 'jev%'" if reread_old else "")
    sql = ("SELECT j.dedupe_key FROM jobs j LEFT JOIN job_requirements r ON r.job_dedupe_key = j.dedupe_key "
           f"WHERE ({missing}) AND LENGTH(COALESCE(j.description, '')) >= ? ORDER BY j.last_seen_at DESC")
    return [r[0] for r in conn.execute(sql + (" LIMIT ?" if limit else ""), (MIN_DESCRIPTION, limit) if limit else (MIN_DESCRIPTION,))]


def queue(conn, limit=None, reread_old=False):
    keys = unread(conn, limit, reread_old)
    for key in keys:  # one transaction: other connections wait for one commit, not thousands
        tasks.enqueue(conn, "extract_job", ref=key, priority=0, commit=False)
    conn.commit()
    return len(keys)


def main():
    from jobhub_poc import config
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--reread-old", action="store_true", help="also re-read jobs read before Jev")
    args = ap.parse_args()
    if config.AI_PAUSED or not config.AI_READ_ALL_JOBS:
        print("not queueing job readings (AI_READ_ALL_JOBS=1 and AI_PAUSED unset turn it on)")
        return
    conn = db.get_connection()
    db.init_db(conn)
    print(f"queued {queue(conn, args.limit, args.reread_old)} job reading(s)")
    conn.close()


if __name__ == "__main__":
    main()
