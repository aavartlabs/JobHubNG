"""Place names: "India" means its cities; cities match their other names (places.py)."""
from datetime import datetime, timezone

from jobhub_poc import places
from jobhub_poc.alerts.rules import Rule, rule_matches
from jobhub_poc.webapp.jobs_listing import parse_list_args, query_jobs


def test_spellings():
    assert "bengaluru" in places.spellings("India") and "gurgaon" in places.spellings(" india ")
    assert set(places.spellings("Bangalore")) == {"bangalore", "bengaluru"}
    assert places.spellings("Berlin") == ("berlin",) and places.spellings("") == ()


def test_an_india_alert_matches_jobs_that_only_name_a_city():
    rule = Rule(locations=("India",))
    assert rule_matches(rule, {"location": "Hyderabad, Telangana"})
    assert rule_matches(Rule(locations=("Bangalore",)), {"location": "Bengaluru"})
    assert not rule_matches(rule, {"location": "Austin, TX"})


def test_the_jobs_list_finds_indian_cities_when_searching_india(conn):
    now = datetime.now(timezone.utc).isoformat()
    for jid, loc in ((1, "Bengaluru, Karnataka"), (2, "Pune, India"), (3, "Austin, TX")):
        conn.execute("""INSERT INTO jobs (id, dedupe_key, source_site, title, company_name, location, apply_url,
                        description, is_remote, first_seen_at, last_seen_at, raw_json)
                        VALUES (?, ?, 's', 'Engineer', 'Acme', ?, 'https://e.example', 'd', 0, ?, ?, '{}')""",
                     (jid, f"k{jid}", loc, now, now))
    conn.commit()
    ids = sorted(r["id"] for r in query_jobs(conn, parse_list_args({"location": "India"})).rows)
    assert ids == [1, 2]
    assert [r["id"] for r in query_jobs(conn, parse_list_args({"location": "Bangalore"})).rows] == [1]
