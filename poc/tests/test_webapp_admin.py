import re
from datetime import datetime, timedelta, timezone

import pytest
import requests
from werkzeug.security import generate_password_hash

from jobhub_poc import config
from jobhub_poc.webapp import admin as admin_module
from jobhub_poc.webapp.app import create_app

_REAL_SEND_CODE = admin_module._send_code  # before the autouse fake replaces it

USERS_URL = f"{config.AUTH_SERVICE_URL}/internal/admin/users"


@pytest.fixture(autouse=True)
def admin_config(monkeypatch):
    monkeypatch.setattr(config, "AUTH_ADMIN_API_KEY", "admin-key")
    monkeypatch.setattr(config, "ADMIN_MAX_FAILURES", 3)
    monkeypatch.setattr(config, "ADMIN_LOCKOUT_MINUTES", 15)
    monkeypatch.setattr(config, "ADMIN_LOCKOUT_MAX_MINUTES", 60)


@pytest.fixture(autouse=True)
def sent_codes(monkeypatch):
    """The second step: records each code instead of sending it (as if by Telegram)."""
    from jobhub_poc.webapp import admin

    codes = []
    monkeypatch.setattr(admin, "_send_code", lambda code, ip: codes.append(code) or "Telegram")
    return codes


@pytest.fixture
def client(conn, turnstile_calls):
    conn.execute(
        "INSERT INTO app_users (username, password_hash, created_at) VALUES (?, ?, ?)",
        ("admin", generate_password_hash("correct-horse"), "2026-09-16T00:00:00+00:00"),
    )
    conn.commit()
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    return app.test_client()


def _user(user_id="u1", **overrides):
    user = {
        "id": user_id,
        "name": "Ada",
        "email": "ada@example.com",
        "emailVerified": True,
        "phoneNumber": "+15550000001",
        "phoneNumberVerified": True,
        "activeSessions": 1,
        "createdAt": "2026-09-23T10:00:00.000Z",
        "updatedAt": "2026-09-23T10:00:00.000Z",
    }
    user.update(overrides)
    return user


def _login(client, password="correct-horse", username="admin", token="good-token", ip="198.51.100.1"):
    return client.post(
        "/admin/login",
        data={"username": username, "password": password, "cf-turnstile-response": token},
        headers={"CF-Connecting-IP": ip},
    )


def _csrf(client, path="/admin/users"):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def _enter_code(client, code, ip="198.51.100.1"):
    html = client.get("/admin/login/code").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    return client.post("/admin/login/code", data={"csrf_token": token, "code": code},
                       headers={"CF-Connecting-IP": ip})


def _logged_in(client, requests_mock, users=None):
    from jobhub_poc.webapp import admin

    codes = []
    real = admin._send_code
    admin._send_code = lambda code, ip: codes.append(code)
    try:
        requests_mock.get(USERS_URL, json={"users": users if users is not None else [_user()]})
        assert _login(client).status_code == 302
        assert _enter_code(client, codes[-1]).status_code == 302
    finally:
        admin._send_code = real
    return client


def _seed_job(conn):
    conn.execute(
        "INSERT INTO jobs (id, dedupe_key, source_site, title, first_seen_at, last_seen_at, raw_json) "
        "VALUES (1, 'k', 'google', 't', 'x', 'x', '{}')"
    )


# ---- login + brute force ----

def test_admin_pages_redirect_to_login_when_signed_out(client):
    for path in ("/admin", "/admin/users", "/admin/users/u1"):
        resp = client.get(path)
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]


def test_login_page_renders_turnstile_widget(client, monkeypatch):
    monkeypatch.setattr(config, "TURNSTILE_SITEKEY", "sitekey-123")
    html = client.get("/admin/login").get_data(as_text=True)
    assert 'data-sitekey="sitekey-123"' in html
    assert 'data-action="admin_login"' in html


def test_password_then_code_signs_in(client, requests_mock, turnstile_calls, sent_codes):
    requests_mock.get(USERS_URL, json={"users": []})
    resp = _login(client)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/admin/login/code")
    assert turnstile_calls[-1] == ("good-token", "admin_login")
    # The password alone is not a session.
    assert client.get("/admin/users").status_code == 302
    [code] = sent_codes
    assert re.fullmatch(r"[0-9]{6}", code)
    assert "sent a 6-digit code to the admin's Telegram" in client.get("/admin/login/code").get_data(as_text=True)

    resp = _enter_code(client, code)
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/admin/users")
    assert client.get("/admin/users").status_code == 200
    # Used once, gone.
    assert client.application.get_db().execute("SELECT count(*) AS n FROM admin_login_codes").fetchone()["n"] == 0


def test_code_page_needs_a_correct_password_first(client):
    resp = client.get("/admin/login/code")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/admin/login")
    assert client.post("/admin/login/code", data={"code": "123456"}).status_code == 302


def test_code_post_needs_csrf(client, sent_codes):
    _login(client)
    assert client.post("/admin/login/code", data={"code": sent_codes[-1]}).status_code == 400


def test_wrong_codes_run_out_and_count_toward_ip_lockout(client, conn, sent_codes, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_MAX_FAILURES", 10)
    _login(client)
    real = sent_codes[-1]
    wrong = "000000" if real != "000000" else "111111"
    for left in (4, 3, 2, 1):
        resp = _enter_code(client, wrong)
        assert resp.status_code == 401 and f"{left} tries left" in resp.get_data(as_text=True)
    resp = _enter_code(client, wrong)
    assert resp.status_code == 401 and "expired" in resp.get_data(as_text=True)
    # The right code no longer works either: sign in again.
    assert client.get("/admin/login/code").status_code == 302
    row = conn.execute("SELECT failures FROM admin_login_attempts WHERE key = 'ip:198.51.100.1'").fetchone()
    assert row["failures"] == 5


def test_expired_code_is_refused(client, conn, sent_codes):
    _login(client)
    conn.execute("UPDATE admin_login_codes SET expires_at = '2000-01-01T00:00:00+00:00'")
    conn.commit()
    resp = _enter_code(client, sent_codes[-1])
    assert resp.status_code == 401 and "expired" in resp.get_data(as_text=True)
    assert client.get("/admin/users").status_code == 302


def test_code_only_works_in_the_session_that_entered_the_password(client, conn, sent_codes):
    _login(client)
    code = sent_codes[-1]
    other = client.application.test_client()
    assert other.post("/admin/login/code", data={"code": code}).status_code == 302  # no pending sign-in
    assert other.get("/admin/users").status_code == 302


def test_unsent_code_says_so_and_break_glass_code_works(client, conn, monkeypatch, requests_mock):
    from jobhub_poc import admin_codes
    from jobhub_poc.webapp import admin

    def fail(code, ip):
        raise RuntimeError("gateway down")

    monkeypatch.setattr(admin, "_send_code", fail)
    _login(client)
    html = client.get("/admin/login/code").get_data(as_text=True)
    assert "couldn't be sent" in html and "admin_login_code.py" in html

    requests_mock.get(USERS_URL, json={"users": []})
    code = admin_codes.reissue_for_username(conn, "admin")
    assert _enter_code(client, code).status_code == 302
    assert client.get("/admin/users").status_code == 200


def test_send_code_refuses_without_any_admin_channel(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TELEGRAM_CHAT_ID", "")
    monkeypatch.setattr(config, "ADMIN_ALERT_WHATSAPP", "")
    with pytest.raises(RuntimeError, match="ADMIN_ALERT_WHATSAPP"):
        _REAL_SEND_CODE("123456", "198.51.100.1")


def test_send_code_goes_only_to_the_admin_channel(monkeypatch):
    sent = []

    class Sender:
        def telegram(self, chat_id, text):
            sent.append((chat_id, text))

    monkeypatch.setattr(config, "ADMIN_TELEGRAM_CHAT_ID", "4242")
    monkeypatch.setattr(admin_module, "get_senders", lambda backend: Sender())
    assert _REAL_SEND_CODE("123456", "198.51.100.1") == "Telegram"
    [(chat_id, text)] = sent
    assert chat_id == "4242"
    assert "123456" in text and "198.51.100.1" in text


def test_wrong_password_or_unknown_user_is_401_with_one_generic_message(client):
    wrong = _login(client, password="nope")
    unknown = _login(client, username="root")
    assert wrong.status_code == unknown.status_code == 401
    assert "Invalid username or password" in wrong.get_data(as_text=True)
    assert "Invalid username or password" in unknown.get_data(as_text=True)


def test_failed_turnstile_is_403_and_never_checks_the_password(client, conn):
    resp = _login(client, token="forged")
    assert resp.status_code == 403
    assert conn.execute("SELECT count(*) AS n FROM admin_login_attempts").fetchone()["n"] == 0


def test_lockout_after_max_failures_blocks_even_the_right_password(client):
    for _ in range(3):
        assert _login(client, password="nope").status_code == 401
    locked = _login(client)
    assert locked.status_code == 429
    assert "Too many failed attempts" in locked.get_data(as_text=True)


def test_lockout_is_per_username_across_ips(client):
    for i in range(3):
        _login(client, password="nope", ip=f"198.51.100.{i + 10}")
    assert _login(client, ip="203.0.113.50").status_code == 429


def test_lockout_is_per_ip_across_usernames(client):
    for name in ("a", "b", "c"):
        _login(client, username=name, password="nope", ip="198.51.100.77")
    assert _login(client, ip="198.51.100.77").status_code == 429
    # A different IP can still sign in as admin (never failed against "admin").
    assert _login(client, ip="198.51.100.78").status_code == 302


def test_lockout_expires_and_doubles_on_repeat(client, conn):
    for _ in range(3):
        _login(client, password="nope")
    row = conn.execute("SELECT * FROM admin_login_attempts WHERE key = 'user:admin'").fetchone()
    first = datetime.fromisoformat(row["locked_until"]) - datetime.now(timezone.utc)
    assert timedelta(minutes=14) < first <= timedelta(minutes=15)

    # Expire the lock, fail again up to the limit: the next lock is twice as long.
    conn.execute("UPDATE admin_login_attempts SET locked_until = ?", ("2000-01-01T00:00:00+00:00",))
    conn.commit()
    for _ in range(3):
        assert _login(client, password="nope").status_code == 401
    row = conn.execute("SELECT * FROM admin_login_attempts WHERE key = 'user:admin'").fetchone()
    second = datetime.fromisoformat(row["locked_until"]) - datetime.now(timezone.utc)
    assert timedelta(minutes=29) < second <= timedelta(minutes=30)


def test_lockout_duration_is_capped(client, conn):
    conn.execute(
        "INSERT INTO admin_login_attempts (key, failures, lock_count, locked_until, updated_at) "
        "VALUES ('user:admin', 2, 10, NULL, 'x')"
    )
    conn.commit()
    _login(client, password="nope")
    row = conn.execute("SELECT * FROM admin_login_attempts WHERE key = 'user:admin'").fetchone()
    assert datetime.fromisoformat(row["locked_until"]) - datetime.now(timezone.utc) <= timedelta(minutes=60)


def test_success_clears_failure_counters(client, conn, requests_mock):
    requests_mock.get(USERS_URL, json={"users": []})
    _login(client, password="nope")
    _login(client, password="nope")
    assert _login(client).status_code == 302
    assert conn.execute("SELECT count(*) AS n FROM admin_login_attempts").fetchone()["n"] == 0


def test_logout_needs_csrf_and_ends_admin_session(client, requests_mock):
    _logged_in(client, requests_mock)
    assert client.post("/admin/logout").status_code == 400
    assert client.post("/admin/logout", data={"csrf_token": _csrf(client)}).status_code == 302
    assert client.get("/admin/users").status_code == 302


def test_admin_session_does_not_make_you_a_site_user(client, requests_mock):
    _logged_in(client, requests_mock)
    resp = client.get("/alerts")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


# ---- users list ----

def test_users_page_lists_users_state_and_subscription_counts(client, conn, requests_mock):
    conn.execute(
        "INSERT INTO alert_subscriptions (titles, owner_auth_user_id, is_active, created_at, notify_whatsapp) "
        "VALUES ('[\"sre\"]', 'u1', 1, 'x', 1), ('[\"sre\"]', 'u1', 0, 'x', 1)"
    )
    conn.commit()
    _logged_in(client, requests_mock, users=[
        _user(),
        _user("u2", name="Bob", email="bob@example.com", emailVerified=False,
              phoneNumber=None, phoneNumberVerified=False, activeSessions=0),
    ])
    html = client.get("/admin/users").get_data(as_text=True)
    assert requests_mock.last_request.headers["x-admin-api-key"] == "admin-key"
    assert "ada@example.com" in html and "bob@example.com" in html
    assert "1 active / 2" in html
    assert "Pending email" in html
    assert "Verified" in html


def test_users_page_reports_auth_service_errors(client, requests_mock):
    _logged_in(client, requests_mock)
    requests_mock.get(USERS_URL, exc=requests.exceptions.ConnectionError)
    resp = client.get("/admin/users")
    assert resp.status_code == 502
    assert "auth-service" in resp.get_data(as_text=True)


def test_nav_shows_admin_links_only_to_admins(client, requests_mock):
    assert "/admin/users" not in client.get("/jobs").get_data(as_text=True)
    _logged_in(client, requests_mock)
    assert "/admin/users" in client.get("/jobs").get_data(as_text=True)


# ---- edit ----

def test_edit_sends_only_changed_fields(client, requests_mock):
    _logged_in(client, requests_mock)
    patch = requests_mock.patch(f"{USERS_URL}/u1", json={"ok": True})
    resp = client.post("/admin/users/u1", data={
        "csrf_token": _csrf(client), "name": "Ada L", "email": "ada@example.com",
        "phone_number": "+15550000001", "email_verified": "on", "phone_verified": "on",
    })
    assert resp.status_code == 302
    assert patch.last_request.json() == {"name": "Ada L"}


def test_changing_email_or_phone_resets_that_verification(client, requests_mock):
    _logged_in(client, requests_mock)
    patch = requests_mock.patch(f"{USERS_URL}/u1", json={"ok": True})
    client.post("/admin/users/u1", data={
        "csrf_token": _csrf(client), "name": "Ada", "email": "new@example.com",
        "phone_number": "+15550000009", "email_verified": "on", "phone_verified": "on",
    })
    assert patch.last_request.json() == {
        "email": "new@example.com", "emailVerified": False,
        "phoneNumber": "+15550000009", "phoneNumberVerified": False,
    }


def test_verification_flags_can_be_set_by_hand(client, requests_mock):
    _logged_in(client, requests_mock, users=[_user(emailVerified=False, phoneNumberVerified=False)])
    patch = requests_mock.patch(f"{USERS_URL}/u1", json={"ok": True})
    client.post("/admin/users/u1", data={
        "csrf_token": _csrf(client), "name": "Ada", "email": "ada@example.com",
        "phone_number": "+15550000001", "email_verified": "on", "phone_verified": "on",
    })
    assert patch.last_request.json() == {"emailVerified": True, "phoneNumberVerified": True}


def test_edit_with_no_changes_makes_no_call(client, requests_mock):
    _logged_in(client, requests_mock)
    patch = requests_mock.patch(f"{USERS_URL}/u1", json={"ok": True})
    client.post("/admin/users/u1", data={
        "csrf_token": _csrf(client), "name": "Ada", "email": "ada@example.com",
        "phone_number": "+15550000001", "email_verified": "on", "phone_verified": "on",
    })
    assert patch.call_count == 0


def test_edit_surfaces_auth_service_validation_errors(client, requests_mock):
    _logged_in(client, requests_mock)
    requests_mock.patch(f"{USERS_URL}/u1", status_code=409,
                        json={"error": "email or phone number already belongs to another user"})
    resp = client.post("/admin/users/u1", data={
        "csrf_token": _csrf(client), "name": "Ada", "email": "taken@example.com",
        "phone_number": "+15550000001",
    }, follow_redirects=True)
    assert "already belongs to another user" in resp.get_data(as_text=True)


def test_mutations_without_csrf_token_are_rejected(client, requests_mock):
    _logged_in(client, requests_mock)
    patch = requests_mock.patch(f"{USERS_URL}/u1", json={"ok": True})
    delete = requests_mock.delete(f"{USERS_URL}/u1", json={"ok": True})
    revoke = requests_mock.post(f"{USERS_URL}/u1/revoke-sessions", json={"revoked": 1})
    assert client.post("/admin/users/u1", data={"name": "X"}).status_code == 400
    assert client.post("/admin/users/u1/delete", data={"csrf_token": "wrong"}).status_code == 400
    assert client.post("/admin/users/u1/revoke-sessions").status_code == 400
    assert patch.call_count == delete.call_count == revoke.call_count == 0


def test_unknown_user_edit_page_is_404(client, requests_mock):
    _logged_in(client, requests_mock)
    assert client.get("/admin/users/nope").status_code == 404


# ---- revoke + delete ----

def test_revoke_sessions_calls_auth_service(client, requests_mock):
    _logged_in(client, requests_mock)
    revoke = requests_mock.post(f"{USERS_URL}/u1/revoke-sessions", json={"revoked": 2})
    resp = client.post("/admin/users/u1/revoke-sessions", data={"csrf_token": _csrf(client)}, follow_redirects=True)
    assert revoke.call_count == 1
    assert "Signed out 2 session" in resp.get_data(as_text=True)


def test_delete_needs_a_confirmation_page_first(client, requests_mock):
    _logged_in(client, requests_mock)
    html = client.get("/admin/users/u1/delete").get_data(as_text=True)
    assert "ada@example.com" in html
    assert "Delete this user" in html


def test_delete_removes_user_and_their_subscriptions_and_history(client, conn, requests_mock):
    _seed_job(conn)
    conn.execute(
        "INSERT INTO alert_subscriptions (id, titles, owner_auth_user_id, is_active, created_at, notify_whatsapp) "
        "VALUES (10, '[\"sre\"]', 'u1', 1, 'x', 1), (11, '[\"sre\"]', 'u2', 1, 'x', 1)"
    )
    conn.execute(
        "INSERT INTO alerts_sent (subscription_id, job_id, channel, notifier_backend, message, sent_at, status) "
        "VALUES (10, 1, 'whatsapp', 'console', 'm', 'x', 'SENT'), (11, 1, 'whatsapp', 'console', 'm', 'x', 'SENT')"
    )
    conn.commit()
    _logged_in(client, requests_mock)
    delete = requests_mock.delete(f"{USERS_URL}/u1", json={"ok": True})

    resp = client.post("/admin/users/u1/delete", data={"csrf_token": _csrf(client)})

    assert resp.status_code == 302
    assert delete.call_count == 1
    owners = [r["owner_auth_user_id"] for r in conn.execute("SELECT owner_auth_user_id FROM alert_subscriptions")]
    assert owners == ["u2"]
    assert [r["subscription_id"] for r in conn.execute("SELECT subscription_id FROM alerts_sent")] == [11]


def test_failed_auth_service_delete_keeps_subscriptions(client, conn, requests_mock):
    conn.execute(
        "INSERT INTO alert_subscriptions (titles, owner_auth_user_id, is_active, created_at, notify_whatsapp) "
        "VALUES ('[\"sre\"]', 'u1', 1, 'x', 1)"
    )
    conn.commit()
    _logged_in(client, requests_mock)
    requests_mock.delete(f"{USERS_URL}/u1", status_code=500, json={"error": "boom"})

    client.post("/admin/users/u1/delete", data={"csrf_token": _csrf(client)})

    assert conn.execute("SELECT count(*) AS n FROM alert_subscriptions").fetchone()["n"] == 1


def test_edit_normalises_phone_and_refuses_non_international(client, requests_mock):
    _logged_in(client, requests_mock)
    patch = requests_mock.patch(f"{USERS_URL}/u1", json={"ok": True})
    client.post("/admin/users/u1", data={
        "csrf_token": _csrf(client), "name": "Ada", "email": "ada@example.com",
        "phone_number": "+1 555 000 0009", "email_verified": "on", "phone_verified": "on",
    })
    assert patch.last_request.json() == {"phoneNumber": "+15550000009", "phoneNumberVerified": False}

    resp = client.post("/admin/users/u1", data={
        "csrf_token": _csrf(client), "name": "Ada", "email": "ada@example.com",
        "phone_number": "9902065845", "email_verified": "on", "phone_verified": "on",
    }, follow_redirects=True)
    assert patch.call_count == 1
    assert "country code" in resp.get_data(as_text=True)


def test_delete_also_removes_the_users_job_interactions(client, conn, requests_mock):
    conn.execute(
        "INSERT INTO job_interactions (owner_auth_user_id, job_dedupe_key, action, created_at) "
        "VALUES ('u1', 'k', 'view_details', 'x'), ('u2', 'k', 'view_details', 'x')"
    )
    conn.commit()
    _logged_in(client, requests_mock)
    requests_mock.delete(f"{USERS_URL}/u1", json={"ok": True})
    client.post("/admin/users/u1/delete", data={"csrf_token": _csrf(client)})
    owners = [r["owner_auth_user_id"] for r in conn.execute("SELECT owner_auth_user_id FROM job_interactions")]
    assert owners == ["u2"]
