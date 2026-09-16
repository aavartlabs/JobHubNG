"""CLI: match new jobs against active subscriptions and fire notifications."""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jobhub_poc import config, db
from jobhub_poc.alerts.matcher import find_matches
from jobhub_poc.alerts.notifier import get_notifier


def _recent_job_ids(conn, minutes: int) -> list[int]:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    rows = conn.execute("SELECT id FROM jobs WHERE first_seen_at >= ?", (cutoff,)).fetchall()
    return [r["id"] for r in rows]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--new-ids", default=None, help="path to a JSON list of new job ids")
    parser.add_argument("--recent-minutes", type=int, default=10,
                         help="fallback: alert on jobs first_seen_at within the last N minutes")
    args = parser.parse_args()

    conn = db.get_connection()
    db.init_db(conn)

    if args.new_ids:
        new_job_ids = json.loads(Path(args.new_ids).read_text())
    else:
        new_job_ids = _recent_job_ids(conn, args.recent_minutes)

    matches = find_matches(conn, new_job_ids)
    notifier = get_notifier(config.NOTIFIER_BACKEND, conn)
    for match in matches:
        notifier.send(match)

    conn.close()
    print(f"processed {len(matches)} alert match(es) via {config.NOTIFIER_BACKEND} notifier")


if __name__ == "__main__":
    main()
