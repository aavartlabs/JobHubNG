"""Load the bundled fixture into the jobs table.

Useful for an offline-safe demo if live pi05 scraping isn't available: loads
fixtures/sample_everjobs_response_real.json (captured live from pi05,
2026-09-16) so the web UI has something real to show. Alerts belong to a real account
(alerts v2): to try them locally, run auth-service, sign up through the web app, create an
alert at /alerts/register, then `NOTIFIER_BACKEND=console make alerts` to print digests.
"""
import sys
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

    conn.close()


if __name__ == "__main__":
    main()
