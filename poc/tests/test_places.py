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


def test_several_places_and_misspellings():
    wanted, fixes = places.parse("Bengluru, Pune ,, Remote, Hydrabad")
    assert wanted == ["bengaluru", "pune", "remote", "hyderabad"]
    assert fixes == [("Bengluru", "bengaluru"), ("Hydrabad", "hyderabad")]
    assert places.correct("Pune") is None and places.correct("Xyzzyville") is None
    assert places.parse("Wanowarie", extra=["Wanowarie"])[1] == []  # known from the data


def test_the_list_takes_several_places_remote_and_typos(conn):
    now = datetime.now(timezone.utc).isoformat()
    for jid, loc, remote in ((1, "Bengaluru, Karnataka", 0), (2, "Pune, India", 0), (3, "Austin, TX", 0), (4, "Anywhere", 1)):
        conn.execute("""INSERT INTO jobs (id, dedupe_key, source_site, title, company_name, location, apply_url,
                        description, is_remote, first_seen_at, last_seen_at, raw_json)
                        VALUES (?, ?, 's', 'Engineer', 'Acme', ?, 'https://e.example', 'd', ?, ?, ?, '{}')""",
                     (jid, f"k{jid}", loc, remote, now, now))
    conn.commit()
    result = query_jobs(conn, parse_list_args({"location": "Bengluru, Pune, Remote"}))
    assert sorted(r["id"] for r in result.rows) == [1, 2, 4]
    assert result.corrections == (("Bengluru", "bengaluru"),)


def test_an_alert_with_a_misspelled_city_still_matches():
    assert rule_matches(Rule(locations=("Bengluru",)), {"location": "Bangalore, Karnataka"})
