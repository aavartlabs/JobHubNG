"""The active alerts' titles and keywords, handed to pi05's export so the serving DB also
receives warehouse jobs the site's own [serving] search terms don't cover (T14).

    python -m jobhub_poc.alerts.alert_terms --out /tmp/jobhub_alert_terms.json
      -> writes the JSON list, prints its fingerprint (run_pipeline_warehouse.sh compares
         it with the last sync's to decide whether a full re-scan is needed)
"""
import argparse
import hashlib
import json
from pathlib import Path


def active_alert_terms(conn, cap):
    terms = set()
    for row in conn.execute("SELECT titles, keywords FROM alert_subscriptions WHERE is_active = 1"):
        for column in ("titles", "keywords"):
            terms.update(t.strip().lower() for t in json.loads(row[column] or "[]") if t.strip())
    # Capped ([sync] max_alert_terms) so one alert with a huge term list can't pull the
    # whole warehouse into the serving DB.
    return sorted(terms)[:cap]


def terms_fingerprint(terms):
    return hashlib.sha256(json.dumps(sorted(terms)).encode()).hexdigest()[:16]


def main():
    from jobhub_poc import db
    from jobhub_poc.pipeline_config import load_pipeline_config

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    conn = db.get_connection()
    db.init_db(conn)
    terms = active_alert_terms(conn, load_pipeline_config().sync.max_alert_terms)
    conn.close()
    Path(args.out).write_text(json.dumps(terms))
    print(terms_fingerprint(terms))


if __name__ == "__main__":
    main()
