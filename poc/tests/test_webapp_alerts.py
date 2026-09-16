from werkzeug.security import generate_password_hash

from jobhub_poc.webapp.app import create_app


def _logged_in_client(conn):
    conn.execute(
        "INSERT INTO app_users (username, password_hash, created_at) VALUES ('admin', ?, '2026-09-16T00:00:00+00:00')",
        (generate_password_hash("secret"),),
    )
    conn.commit()
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    client = app.test_client()
    client.post("/login", data={"username": "admin", "password": "secret"})
    return client


def test_register_alert_creates_subscription_row(conn):
    client = _logged_in_client(conn)
    resp = client.post("/alerts/register", data={
        "phone_number": "+15551234567",
        "title_keyword": "engineer",
        "location_keyword": "remote",
    })
    assert resp.status_code in (200, 302)
    row = conn.execute("SELECT * FROM alert_subscriptions WHERE phone_number = '+15551234567'").fetchone()
    assert row is not None
    assert row["title_keyword"] == "engineer"


def test_register_alert_malformed_phone_returns_400(conn):
    client = _logged_in_client(conn)
    resp = client.post("/alerts/register", data={"phone_number": "not-a-phone"})
    assert resp.status_code == 400
    count = conn.execute("SELECT COUNT(*) AS c FROM alert_subscriptions").fetchone()["c"]
    assert count == 0


def test_register_alert_requires_login(conn):
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    client = app.test_client()
    resp = client.post("/alerts/register", data={"phone_number": "+15551234567"})
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
