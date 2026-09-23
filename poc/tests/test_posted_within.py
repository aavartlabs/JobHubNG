import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from jobhub_poc import db
from jobhub_poc.loader.load_dump import upsert_job
from jobhub_poc.webapp.app import create_app


def _iso(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _seed(conn, key, posted_source, first_seen_days_ago, title="SRE"):
    job = {"id": key, "title": title, "companyName": "Acme", "site": "acme", "datePosted": posted_source}
    upsert_job(conn, job, key, _iso(first_seen_days_ago), _iso(0))
    conn.commit()


def _api(conn, query):
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    return json.loads(app.test_client().get(f"/api/jobs?{query}").data)


def test_upsert_normalises_posted_at(conn):
    _seed(conn, "a", "2026-07-15T18:14:31-04:00", 1)
    assert conn.execute("SELECT posted_at FROM jobs").fetchone()["posted_at"] == "2026-07-15T22:14:31+00:00"


def test_posted_within_uses_posted_date_or_falls_back_to_first_seen(conn):
    _seed(conn, "fresh-post", _iso(1)[:10], 0)           # posted yesterday, seen today
    _seed(conn, "old-post", _iso(20)[:10], 1)            # posted 20d ago, only seen yesterday
    _seed(conn, "no-date-new", None, 2)                  # no date, seen 2 days ago
    _seed(conn, "no-date-old", None, 10)                 # no date, seen 10 days ago
    data = _api(conn, "posted_within=3&page_size=100")
    assert data["total"] == 2
    ids = {j["id"] for j in data["jobs"]}
    got = {r["dedupe_key"] for r in conn.execute(
        f"SELECT dedupe_key FROM jobs WHERE id IN ({','.join(map(str, ids))})")}
    assert got == {"fresh-post", "no-date-new"}


@pytest.mark.parametrize("bad", ["2", "abc", "-1", "365"])
def test_unknown_posted_within_values_are_ignored(conn, bad):
    _seed(conn, "old", _iso(200)[:10], 200)
    assert _api(conn, f"posted_within={bad}")["total"] == 1


def test_recently_posted_sort_orders_by_posted_then_first_seen(conn):
    _seed(conn, "a", _iso(5)[:10], 0, title="posted 5d")
    _seed(conn, "b", _iso(1)[:10], 0, title="posted 1d")
    _seed(conn, "c", None, 3, title="no date, seen 3d")
    titles = [j["title"] for j in _api(conn, "sort=posted&page_size=10")["jobs"]]
    assert titles == ["posted 1d", "no date, seen 3d", "posted 5d"]


def test_a_posted_date_later_than_first_seen_is_clamped(conn):
    """A job can't be posted after we already scraped it (e.g. a re-posting bump)."""
    _seed(conn, "bumped", _iso(1)[:10], 30)
    assert _api(conn, "posted_within=7")["total"] == 0


def test_list_includes_posted_at(conn):
    _seed(conn, "a", "2026-08-27", 1)
    job = _api(conn, "")["jobs"][0]
    assert job["posted_at"] == "2026-08-27T00:00:00+00:00"


def test_existing_db_gets_posted_at_column_and_backfill(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, dedupe_key TEXT NOT NULL UNIQUE,
            external_job_id TEXT, source_site TEXT NOT NULL, search_term TEXT, title TEXT NOT NULL,
            company_name TEXT, location TEXT, description TEXT, employment_type TEXT,
            is_remote INTEGER NOT NULL DEFAULT 0, apply_url TEXT, posted_at_source TEXT,
            first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, raw_json TEXT NOT NULL);
        INSERT INTO jobs (dedupe_key, source_site, title, posted_at_source, first_seen_at, last_seen_at, raw_json)
        VALUES ('a', 's', 't', '1788323485', '2026-09-23T00:00:00+00:00', '2026-09-23T00:00:00+00:00', '{}'),
               ('b', 's', 't', NULL,         '2026-09-23T00:00:00+00:00', '2026-09-23T00:00:00+00:00', '{}');
    """)
    old.close()
    conn = db.get_connection(str(path))
    db.init_db(conn)
    rows = dict(conn.execute("SELECT dedupe_key, posted_at FROM jobs").fetchall())
    assert rows == {"a": "2026-09-02T04:31:25+00:00", "b": None}
    db.init_db(conn)  # idempotent
