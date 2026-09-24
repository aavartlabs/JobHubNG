import json

import pytest

from jobhub_poc import config
from jobhub_poc.webapp.app import create_app

SESSION_COOKIE_NAME = "jobhub-auth.session_token"
GET_SESSION_URL = f"{config.AUTH_SERVICE_URL}/auth/get-session"


def _user(user_id="auth-user-1"):
    return {"id": user_id, "email": "seeker@example.com", "name": "Job Seeker", "emailVerified": True,
            "telegramVerified": True, "telegramChatId": "4242", "telegramUsername": "seeker"}


def _client(conn, requests_mock, user_id="auth-user-1"):
    requests_mock.get(GET_SESSION_URL, json={"session": {}, "user": _user(user_id)})
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    client = app.test_client()
    client.set_cookie(SESSION_COOKIE_NAME, "fake")
    return client


def _form(**overrides):
    form = {"titles": "SRE, DevOps, sre", "locations": "Bangalore, Remote", "companies": "", "keywords": "",
            "work_mode": "", "notify_email": "on", "notify_telegram": "on", "cf-turnstile-response": "good-token"}
    form.update(overrides)
    return form


def _subs(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM alert_subscriptions ORDER BY id")]


def test_register_form_has_no_address_field_and_shows_the_contacts(conn, requests_mock):
    html = _client(conn, requests_mock).get("/alerts/register").get_data(as_text=True)
    assert 'name="phone_number"' not in html
    assert "se•••@example.com" in html and "@seeker" in html
    assert "notify_whatsapp" not in html
    for field in ("titles", "locations", "companies", "keywords", "work_mode", "notify_email", "notify_telegram"):
        assert f'name="{field}"' in html


def test_register_stores_normalised_multi_value_rule_and_channels(conn, requests_mock, turnstile_calls):
    resp = _client(conn, requests_mock, "auth-user-42").post("/alerts/register", data=_form(work_mode="remote"))
    assert resp.status_code == 302
    [sub] = _subs(conn)
    assert sub["owner_auth_user_id"] == "auth-user-42"
    assert json.loads(sub["titles"]) == ["sre", "devops"]
    assert json.loads(sub["locations"]) == ["bangalore", "remote"]
    assert (sub["work_mode"], sub["notify_email"], sub["notify_telegram"]) == ("remote", 1, 1)
    assert turnstile_calls[-1] == ("good-token", "alert_register")


@pytest.mark.parametrize("overrides,message", [
    ({"titles": "", "locations": "", "work_mode": ""}, "at least one"),
    ({"notify_email": "", "notify_telegram": ""}, "email or Telegram"),
    ({"titles": ",".join(f"t{i}" for i in range(11))}, "10"),
    ({"titles": "x" * 61}, "60"),
    ({"work_mode": "hybrid"}, "work mode"),
])
def test_invalid_alerts_are_rejected_with_a_reason(conn, requests_mock, turnstile_calls, overrides, message):
    resp = _client(conn, requests_mock).post("/alerts/register", data=_form(**overrides))
    assert resp.status_code == 400
    assert message in resp.get_data(as_text=True)
    assert _subs(conn) == []


def test_work_mode_alone_is_a_valid_filter(conn, requests_mock, turnstile_calls):
    resp = _client(conn, requests_mock).post("/alerts/register", data=_form(titles="", locations="", work_mode="remote"))
    assert resp.status_code == 302


def test_register_without_valid_turnstile_is_rejected(conn, requests_mock, turnstile_calls):
    resp = _client(conn, requests_mock).post("/alerts/register", data=_form(**{"cf-turnstile-response": "forged"}))
    assert resp.status_code == 403
    assert _subs(conn) == []


def test_register_requires_login(conn, requests_mock):
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    resp = app.test_client().post("/alerts/register", data=_form())
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]


def test_list_shows_only_own_alerts_with_readable_criteria(conn, requests_mock, turnstile_calls):
    mine = _client(conn, requests_mock, "me")
    mine.post("/alerts/register", data=_form())
    other = _client(conn, requests_mock, "someone-else")
    other.post("/alerts/register", data=_form(titles="Chef"))
    html = _client(conn, requests_mock, "me").get("/alerts").get_data(as_text=True)
    assert "sre, devops · bangalore, remote" in html
    assert "chef" not in html
    assert "Email" in html and "Telegram" in html


def test_pause_resume_and_delete_own_alert(conn, requests_mock, turnstile_calls):
    client = _client(conn, requests_mock, "me")
    client.post("/alerts/register", data=_form())
    sub_id = _subs(conn)[0]["id"]
    client.post(f"/alerts/{sub_id}/pause")
    assert _subs(conn)[0]["is_active"] == 0
    client.post(f"/alerts/{sub_id}/resume")
    assert _subs(conn)[0]["is_active"] == 1
    client.post(f"/alerts/{sub_id}/delete")
    assert _subs(conn) == []


def test_cannot_touch_another_users_alert(conn, requests_mock, turnstile_calls):
    _client(conn, requests_mock, "owner").post("/alerts/register", data=_form())
    sub_id = _subs(conn)[0]["id"]
    intruder = _client(conn, requests_mock, "intruder")
    for action in ("pause", "delete"):
        intruder.post(f"/alerts/{sub_id}/{action}")
    assert _subs(conn)[0]["is_active"] == 1


def test_delete_removes_the_alert_history_too(conn, requests_mock, turnstile_calls):
    client = _client(conn, requests_mock, "me")
    client.post("/alerts/register", data=_form())
    sub_id = _subs(conn)[0]["id"]
    job = conn.execute("INSERT INTO jobs (dedupe_key, source_site, title, first_seen_at, last_seen_at, raw_json) "
                       "VALUES ('k', 's', 'SRE', 'x', 'x', '{}')").lastrowid
    conn.execute("INSERT INTO alerts_sent (subscription_id, job_id, channel, notifier_backend, message, sent_at, status) "
                 "VALUES (?, ?, 'email', 'live', 'm', 's', 'SENT')", (sub_id, job))
    conn.commit()
    client.post(f"/alerts/{sub_id}/delete")
    assert conn.execute("SELECT count(*) FROM alerts_sent").fetchone()[0] == 0


def test_actions_reject_get(conn, requests_mock):
    client = _client(conn, requests_mock)
    for action in ("pause", "resume", "delete"):
        assert client.get(f"/alerts/1/{action}").status_code == 405


def _client_without_telegram(conn, requests_mock):
    user = {**_user(), "telegramVerified": None, "telegramChatId": None, "telegramUsername": None}
    requests_mock.get(GET_SESSION_URL, json={"session": {}, "user": user})
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    client = app.test_client()
    client.set_cookie(SESSION_COOKIE_NAME, "fake-session-token")
    return client


def test_without_telegram_the_option_is_disabled_with_a_connect_link(conn, requests_mock):
    html = _client_without_telegram(conn, requests_mock).get("/alerts/register").get_data(as_text=True)
    assert 'name="notify_telegram" disabled' in html and "Connect Telegram" in html


def test_telegram_alerts_need_telegram_linked(conn, requests_mock, turnstile_calls):
    client = _client_without_telegram(conn, requests_mock)
    resp = client.post("/alerts/register", data=_form(notify_email="", notify_telegram="on"))
    assert resp.status_code == 400 and "Connect Telegram first" in resp.get_data(as_text=True)
    assert conn.execute("SELECT count(*) FROM alert_subscriptions").fetchone()[0] == 0
    # Email-only alerts are fine without Telegram.
    assert client.post("/alerts/register", data=_form(notify_telegram="")).status_code == 302
