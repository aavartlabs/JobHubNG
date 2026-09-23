"""CLI: match newly-loaded jobs against active alerts and send one digest per alert per
channel. NOTIFIER_BACKEND=console prints the digests instead of sending (dry run)."""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jobhub_poc import config, db
from jobhub_poc.alerts.contacts import load_contacts
from jobhub_poc.alerts.delivery import deliver
from jobhub_poc.alerts.matcher import find_matches
from jobhub_poc.alerts.senders import get_senders


def _recent_job_ids(conn, minutes: int) -> list[int]:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    return [r["id"] for r in conn.execute("SELECT id FROM jobs WHERE first_seen_at >= ?", (cutoff,))]


def run(conn, new_job_ids, backend):
    matches = find_matches(conn, new_job_ids)
    if not matches:
        return {"matched_alerts": 0}
    # Before anything is written: without contacts there is no safe way to deliver.
    contacts = load_contacts()
    stats = deliver(conn, matches, contacts, get_senders(backend), backend, config.WEB_ORIGIN)
    return {"matched_alerts": len(matches), **stats}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--new-ids", default=None, help="path to a JSON list of new job ids")
    parser.add_argument("--recent-minutes", type=int, default=10,
                        help="fallback: alert on jobs first_seen_at within the last N minutes")
    args = parser.parse_args()

    conn = db.get_connection()
    db.init_db(conn)
    new_job_ids = (json.loads(Path(args.new_ids).read_text()) if args.new_ids
                   else _recent_job_ids(conn, args.recent_minutes))
    result = run(conn, new_job_ids, config.NOTIFIER_BACKEND)
    conn.close()
    print(f"alerts ({config.NOTIFIER_BACKEND}): {json.dumps(result)}")


if __name__ == "__main__":
    main()
