"""Load the bundled fixture and register one demo alert subscription.

Useful for an offline-safe demo if live pi05 scraping isn't available: loads
fixtures/sample_everjobs_response_real.json (captured live from pi05,
2026-09-16) so the web UI and alert flow have something real to show.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobhub_poc import db
from jobhub_poc.loader.load_dump import load_dump

_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample_everjobs_response_real.json"


def main() -> None:
    conn = db.get_connection()
    db.init_db(conn)

    new_ids = load_dump(conn, _FIXTURE)
    print(f"loaded fixture, {len(new_ids)} new job(s)")

    existing = conn.execute(
        "SELECT id FROM alert_subscriptions WHERE phone_number = '+15550000000'"
    ).fetchone()
    if not existing:
        conn.execute(
            """
            INSERT INTO alert_subscriptions (phone_number, title_keyword, location_keyword, is_active, created_at)
            VALUES ('+15550000000', 'engineer', NULL, 1, ?)
            """,
            (datetime.now(timezone.utc).isoformat(),),
        )
        conn.commit()
        print("registered demo alert subscription (+15550000000, title contains 'engineer')")
    else:
        print("demo alert subscription already exists, skipping")

    conn.close()


if __name__ == "__main__":
    main()
