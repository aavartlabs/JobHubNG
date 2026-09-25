"""Delete serving jobs not seen in any sweep for [retention] serving_retention_days
(config/pipeline.ini).

Keyed on last_seen_at (refreshed every time a sweep or delta still lists the job), never
on the source's posted date -- real EverJobs data showed posted dates ranging from
same-day to years stale -- and no longer on first_seen_at, which purged listings that
were still live 15 days after we first found them.

alerts_sent rows for purged jobs go first: alerts_sent.job_id references jobs(id) and
foreign keys are on, so deleting an alerted job on its own fails.

It also keeps activity records from growing forever (tidy()): finished AI tasks after
AI_TASKS_KEEP_DAYS, job views and Apply clicks after INTERACTIONS_KEEP_DAYS, and match
evidence and job readings for jobs no longer listed.
"""
import argparse
import sqlite3
from datetime import datetime, timedelta, timezone


def purge(conn: sqlite3.Connection, window_days: int, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=window_days)).isoformat()
    with conn:
        conn.execute(
            "DELETE FROM alerts_sent WHERE job_id IN (SELECT id FROM jobs WHERE last_seen_at < ?)", (cutoff,))
        cur = conn.execute("DELETE FROM jobs WHERE last_seen_at < ?", (cutoff,))
    return cur.rowcount


AI_TASKS_KEEP_DAYS = 30
INTERACTIONS_KEEP_DAYS = 180


def tidy(conn: sqlite3.Connection, now: datetime | None = None) -> dict:
    """Activity records past their keep period, and derived rows whose job is gone."""
    now = now or datetime.now(timezone.utc)
    tasks_cutoff = (now - timedelta(days=AI_TASKS_KEEP_DAYS)).isoformat()
    views_cutoff = (now - timedelta(days=INTERACTIONS_KEEP_DAYS)).isoformat()
    with conn:
        counts = {
            "ai_tasks": conn.execute("DELETE FROM ai_tasks WHERE status IN ('done', 'failed') AND updated_at < ?",
                                     (tasks_cutoff,)).rowcount,
            "job_interactions": conn.execute("DELETE FROM job_interactions WHERE created_at < ?",
                                             (views_cutoff,)).rowcount,
            "match_evidence": conn.execute("DELETE FROM match_evidence WHERE job_dedupe_key NOT IN "
                                           "(SELECT dedupe_key FROM jobs)").rowcount,
            "job_requirements": conn.execute("DELETE FROM job_requirements WHERE job_dedupe_key NOT IN "
                                             "(SELECT dedupe_key FROM jobs)").rowcount,
        }
    return counts


def default_window_days() -> int:
    from jobhub_poc.pipeline_config import load_pipeline_config

    return load_pipeline_config().retention.serving_retention_days


def main() -> None:
    from jobhub_poc import db

    parser = argparse.ArgumentParser()
    parser.add_argument("--window-days", type=int, default=None,
                        help="override [retention] serving_retention_days from pipeline.ini")
    args = parser.parse_args()
    window_days = args.window_days if args.window_days is not None else default_window_days()

    conn = db.get_connection()
    db.init_db(conn)
    deleted = purge(conn, window_days)
    tidied = tidy(conn)
    conn.close()
    print(f"purged {deleted} job(s) not seen for {window_days} days; tidied {tidied}")


if __name__ == "__main__":
    main()
