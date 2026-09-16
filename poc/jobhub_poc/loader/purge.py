"""Delete jobs whose first_seen_at is older than the purge window.

Deliberately keyed on first_seen_at (our own discovery timestamp), never on
the source's own posted-date -- real EverJobs data showed posted dates
ranging from same-day to multiple years stale, so it can't drive purging.
"""
import argparse
import sqlite3
from datetime import datetime, timedelta, timezone


def purge(conn: sqlite3.Connection, window_days: int, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=window_days)).isoformat()
    cur = conn.execute("DELETE FROM jobs WHERE first_seen_at < ?", (cutoff,))
    conn.commit()
    return cur.rowcount


def main() -> None:
    from jobhub_poc import config, db

    parser = argparse.ArgumentParser()
    parser.add_argument("--window-days", type=int, default=config.PURGE_WINDOW_DAYS)
    args = parser.parse_args()

    conn = db.get_connection()
    db.init_db(conn)
    deleted = purge(conn, args.window_days)
    conn.close()
    print(f"purged {deleted} job(s) older than {args.window_days} days")


if __name__ == "__main__":
    main()
