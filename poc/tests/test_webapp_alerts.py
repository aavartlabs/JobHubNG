from jobhub_poc import config
from jobhub_poc.webapp.app import create_app

SESSION_COOKIE_NAME = "jobhub-auth.session_token"
GET_SESSION_URL = f"{config.AUTH_SERVICE_URL}/auth/get-session"


def _user(user_id="auth-user-1"):
    return {
        "id": user_id,
        "email": "seeker@example.com",
        "name": "Job Seeker",
        "emailVerified": True,
        "phoneNumberVerified": True,
        "phoneNumber": "+15551234567",
    }


def _logged_in_client(conn, requests_mock, user_id="auth-user-1"):
    requests_mock.get(GET_SESSION_URL, json={"session": {}, "user": _user(user_id=user_id)})
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    client = app.test_client()
    client.set_cookie(SESSION_COOKIE_NAME, "fake-session-token")
    return client


def _seed_subscription(conn, owner_id, phone="+15550001111"):
    cur = conn.execute(
        """
        INSERT INTO alert_subscriptions
            (phone_number, title_keyword, location_keyword, owner_auth_user_id, is_active, created_at)
        VALUES (?, NULL, NULL, ?, 1, '2026-09-16T00:00:00+00:00')
        """,
        (phone, owner_id),
    )
    conn.commit()
    return cur.lastrowid


def test_register_alert_creates_subscription_row(conn, requests_mock):
    client = _logged_in_client(conn, requests_mock)
    resp = client.post("/alerts/register", data={
        "phone_number": "+15551234567",
        "title_keyword": "engineer",
        "location_keyword": "remote",
    })
    assert resp.status_code in (200, 302)
    row = conn.execute("SELECT * FROM alert_subscriptions WHERE phone_number = '+15551234567'").fetchone()
    assert row is not None
    assert row["title_keyword"] == "engineer"


def test_register_alert_stamps_current_users_owner_id(conn, requests_mock):
    client = _logged_in_client(conn, requests_mock, user_id="auth-user-42")
    client.post("/alerts/register", data={"phone_number": "+15551234567"})
    row = conn.execute("SELECT * FROM alert_subscriptions WHERE phone_number = '+15551234567'").fetchone()
    assert row["owner_auth_user_id"] == "auth-user-42"


def test_register_alert_malformed_phone_returns_400(conn, requests_mock):
    client = _logged_in_client(conn, requests_mock)
    resp = client.post("/alerts/register", data={"phone_number": "not-a-phone"})
    assert resp.status_code == 400
    count = conn.execute("SELECT COUNT(*) AS c FROM alert_subscriptions").fetchone()["c"]
    assert count == 0


def test_register_alert_requires_login(conn, requests_mock):
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    client = app.test_client()
    resp = client.post("/alerts/register", data={"phone_number": "+15551234567"})
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
    # No session cookie -> load_current_user must short-circuit without calling out.
    assert requests_mock.call_count == 0


def test_alerts_list_requires_login(conn, requests_mock):
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    resp = app.test_client().get("/alerts")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
    assert requests_mock.call_count == 0


def test_alerts_list_only_shows_current_users_own_subscriptions(conn, requests_mock):
    _seed_subscription(conn, "auth-user-1", phone="+15550001111")
    _seed_subscription(conn, "auth-user-2", phone="+15559998888")
    client = _logged_in_client(conn, requests_mock, user_id="auth-user-1")

    resp = client.get("/alerts")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert "+15550001111" in body
    assert "+15559998888" not in body


def test_deactivate_own_subscription_succeeds(conn, requests_mock):
    sub_id = _seed_subscription(conn, "auth-user-1")
    client = _logged_in_client(conn, requests_mock, user_id="auth-user-1")

    resp = client.post(f"/alerts/{sub_id}/deactivate")

    assert resp.status_code in (200, 302)
    row = conn.execute("SELECT is_active FROM alert_subscriptions WHERE id = ?", (sub_id,)).fetchone()
    assert row["is_active"] == 0


def test_deactivate_requires_login(conn, requests_mock):
    sub_id = _seed_subscription(conn, "auth-user-1")
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    resp = app.test_client().post(f"/alerts/{sub_id}/deactivate")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
    assert requests_mock.call_count == 0
    row = conn.execute("SELECT is_active FROM alert_subscriptions WHERE id = ?", (sub_id,)).fetchone()
    assert row["is_active"] == 1


def test_deactivate_another_users_subscription_is_unaffected(conn, requests_mock):
    other_sub_id = _seed_subscription(conn, "auth-user-2")
    client = _logged_in_client(conn, requests_mock, user_id="auth-user-1")

    resp = client.post(f"/alerts/{other_sub_id}/deactivate")

    assert resp.status_code in (200, 302)
    row = conn.execute("SELECT is_active FROM alert_subscriptions WHERE id = ?", (other_sub_id,)).fetchone()
    assert row["is_active"] == 1


def test_deactivate_nonexistent_subscription_is_a_no_op(conn, requests_mock):
    client = _logged_in_client(conn, requests_mock, user_id="auth-user-1")
    resp = client.post("/alerts/999999/deactivate")
    assert resp.status_code in (200, 302)
