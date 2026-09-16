import json

from werkzeug.security import generate_password_hash

from jobhub_poc.webapp.app import create_app


def _seed_user(conn):
    conn.execute(
        "INSERT INTO app_users (username, password_hash, created_at) VALUES ('admin', ?, '2026-09-16T00:00:00+00:00')",
        (generate_password_hash("secret"),),
    )
    conn.commit()


def _seed_job(conn, dedupe_key, title, location, first_seen_at, company_name="Acme", apply_url=None):
    conn.execute(
        """
        INSERT INTO jobs (dedupe_key, source_site, title, company_name, location, apply_url, first_seen_at, last_seen_at, raw_json)
        VALUES (?, 'acme', ?, ?, ?, ?, ?, ?, '{}')
        """,
        (dedupe_key, title, company_name, location, apply_url, first_seen_at, first_seen_at),
    )
    conn.commit()


def _logged_in_client(conn):
    _seed_user(conn)
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    client = app.test_client()
    client.post("/login", data={"username": "admin", "password": "secret"})
    return client


def test_api_jobs_requires_login(conn):
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    resp = app.test_client().get("/api/jobs")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_api_jobs_returns_json_shape(conn):
    _seed_job(conn, "1", "Software Engineer", "Remote", "2026-09-16T10:00:00+00:00",
              apply_url="https://example.com/1")
    client = _logged_in_client(conn)
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    assert resp.content_type.startswith("application/json")
    data = json.loads(resp.data)
    assert data["count"] == 1
    job = data["jobs"][0]
    assert job["title"] == "Software Engineer"
    assert job["company_name"] == "Acme"
    assert job["location"] == "Remote"
    assert job["apply_url"] == "https://example.com/1"
    assert "first_seen_at" in job


def test_api_jobs_title_filter(conn):
    _seed_job(conn, "1", "Senior Data Engineer", "Remote", "2026-09-16T10:00:00+00:00")
    _seed_job(conn, "2", "Sales Associate", "Remote", "2026-09-16T09:00:00+00:00")
    client = _logged_in_client(conn)
    resp = client.get("/api/jobs?title=engineer")
    data = json.loads(resp.data)
    titles = [j["title"] for j in data["jobs"]]
    assert titles == ["Senior Data Engineer"]


def test_api_jobs_location_filter(conn):
    _seed_job(conn, "1", "Engineer", "Bengaluru, India", "2026-09-16T10:00:00+00:00")
    _seed_job(conn, "2", "Engineer", "Remote", "2026-09-16T09:00:00+00:00")
    client = _logged_in_client(conn)
    resp = client.get("/api/jobs?location=bengaluru")
    data = json.loads(resp.data)
    assert len(data["jobs"]) == 1
    assert "Bengaluru" in data["jobs"][0]["location"]


def test_api_jobs_default_sort_is_freshness_descending(conn):
    _seed_job(conn, "1", "Older Job", "Remote", "2026-09-14T10:00:00+00:00")
    _seed_job(conn, "2", "Newer Job", "Remote", "2026-09-16T10:00:00+00:00")
    client = _logged_in_client(conn)
    resp = client.get("/api/jobs")
    data = json.loads(resp.data)
    titles = [j["title"] for j in data["jobs"]]
    assert titles == ["Newer Job", "Older Job"]


def test_api_jobs_sort_title_ascending(conn):
    _seed_job(conn, "1", "Zebra Role", "Remote", "2026-09-16T10:00:00+00:00")
    _seed_job(conn, "2", "Alpha Role", "Remote", "2026-09-16T09:00:00+00:00")
    client = _logged_in_client(conn)
    resp = client.get("/api/jobs?sort=title")
    data = json.loads(resp.data)
    titles = [j["title"] for j in data["jobs"]]
    assert titles == ["Alpha Role", "Zebra Role"]
