from werkzeug.security import generate_password_hash

from jobhub_poc.webapp.app import create_app


def _seed_user(conn):
    conn.execute(
        "INSERT INTO app_users (username, password_hash, created_at) VALUES ('admin', ?, '2026-09-16T00:00:00+00:00')",
        (generate_password_hash("secret"),),
    )
    conn.commit()


def _seed_job(conn, dedupe_key, title, location, first_seen_at):
    conn.execute(
        """
        INSERT INTO jobs (dedupe_key, source_site, title, location, first_seen_at, last_seen_at, raw_json)
        VALUES (?, 'acme', ?, ?, ?, ?, '{}')
        """,
        (dedupe_key, title, location, first_seen_at, first_seen_at),
    )
    conn.commit()


def _logged_in_client(conn):
    _seed_user(conn)
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    client = app.test_client()
    client.post("/login", data={"username": "admin", "password": "secret"})
    return client


def test_title_filter_narrows_results(conn):
    _seed_job(conn, "1", "Senior Data Engineer", "Remote", "2026-09-16T10:00:00+00:00")
    _seed_job(conn, "2", "Sales Associate", "Remote", "2026-09-16T09:00:00+00:00")
    client = _logged_in_client(conn)
    resp = client.get("/jobs?title=engineer")
    assert b"Data Engineer" in resp.data
    assert b"Sales Associate" not in resp.data


def test_location_filter_narrows_results(conn):
    _seed_job(conn, "1", "Engineer", "Bengaluru, India", "2026-09-16T10:00:00+00:00")
    _seed_job(conn, "2", "Engineer", "Remote", "2026-09-16T09:00:00+00:00")
    client = _logged_in_client(conn)
    resp = client.get("/jobs?location=bengaluru")
    assert b"Bengaluru" in resp.data
    assert resp.data.count(b"<tr") <= 2  # header row (if any) + exactly one job row


def test_jobs_sorted_by_freshness_descending_by_default(conn):
    _seed_job(conn, "1", "Older Job", "Remote", "2026-09-14T10:00:00+00:00")
    _seed_job(conn, "2", "Newer Job", "Remote", "2026-09-16T10:00:00+00:00")
    client = _logged_in_client(conn)
    resp = client.get("/jobs")
    body = resp.data.decode()
    assert body.index("Newer Job") < body.index("Older Job")
