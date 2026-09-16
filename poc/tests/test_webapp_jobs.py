from werkzeug.security import generate_password_hash

from jobhub_poc.webapp.app import create_app


def _seed_user(conn):
    conn.execute(
        "INSERT INTO app_users (username, password_hash, created_at) VALUES ('admin', ?, '2026-09-16T00:00:00+00:00')",
        (generate_password_hash("secret"),),
    )
    conn.commit()


def _logged_in_client(conn):
    _seed_user(conn)
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    client = app.test_client()
    client.post("/login", data={"username": "admin", "password": "secret"})
    return client


# Filter/sort behavior itself is exercised against /api/jobs in
# tests/test_webapp_api.py -- these tests only cover that /jobs serves the
# shell the TypeScript bundle (static/app.js) expects to find.


def test_jobs_page_requires_login(conn):
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    resp = app.test_client().get("/jobs")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_jobs_page_serves_shell_with_expected_elements(conn):
    client = _logged_in_client(conn)
    resp = client.get("/jobs")
    assert resp.status_code == 200
    body = resp.data.decode()
    for expected_id in ("filter-form", "title-input", "location-input", "sort-select", "jobs-body"):
        assert f'id="{expected_id}"' in body
    assert "static/app.js" in body
