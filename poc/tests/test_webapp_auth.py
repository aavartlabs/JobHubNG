from werkzeug.security import generate_password_hash

from jobhub_poc.webapp.app import create_app


def _seed_user(conn, username="admin", password="secret"):
    conn.execute(
        "INSERT INTO app_users (username, password_hash, created_at) VALUES (?, ?, '2026-09-16T00:00:00+00:00')",
        (username, generate_password_hash(password)),
    )
    conn.commit()


def _app_and_client(conn):
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    return app, app.test_client()


def test_jobs_route_requires_login_redirects(conn):
    _app, client = _app_and_client(conn)
    resp = client.get("/jobs")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_login_valid_credentials_sets_session(conn):
    _seed_user(conn)
    _app, client = _app_and_client(conn)
    resp = client.post("/login", data={"username": "admin", "password": "secret"})
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get("user_id") is not None


def test_login_invalid_credentials_rejected(conn):
    _seed_user(conn)
    _app, client = _app_and_client(conn)
    resp = client.post("/login", data={"username": "admin", "password": "wrong"})
    assert resp.status_code == 200  # re-renders login form
    with client.session_transaction() as sess:
        assert sess.get("user_id") is None


def test_logged_in_user_can_reach_jobs(conn):
    _seed_user(conn)
    _app, client = _app_and_client(conn)
    client.post("/login", data={"username": "admin", "password": "secret"})
    resp = client.get("/jobs")
    assert resp.status_code == 200
