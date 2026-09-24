import pytest
import requests

from jobhub_poc import config
from jobhub_poc.webapp.app import create_app

SESSION_COOKIE_NAME = "jobhub-auth.session_token"
GET_SESSION_URL = f"{config.AUTH_SERVICE_URL}/auth/get-session"
SIGN_OUT_URL = f"{config.AUTH_SERVICE_URL}/auth/sign-out"


def _user(email_verified=True, telegram_verified=True, user_id="auth-user-1"):
    return {
        "id": user_id,
        "email": "seeker@example.com",
        "name": "Job Seeker",
        "emailVerified": email_verified,
        # `null`, not `false`, until Telegram is linked -- exercised directly below
        # rather than always using bool.
        "telegramVerified": telegram_verified,
        "telegramChatId": "4242",
    }


def _app_and_client(conn):
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    return app, app.test_client()


def test_gated_route_with_get_session_connection_error_redirects_to_login(conn, requests_mock):
    """Test /alerts/register (gated route) handles auth service connection error by redirecting to login."""
    requests_mock.get(GET_SESSION_URL, exc=requests.exceptions.ConnectionError)
    _app, client = _app_and_client(conn)
    client.set_cookie(SESSION_COOKIE_NAME, "fake-session-token")
    resp = client.get("/alerts/register")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_gated_route_with_get_session_timeout_redirects_to_login(conn, requests_mock):
    """Test /alerts/register (gated route) handles auth service timeout by redirecting to login."""
    requests_mock.get(GET_SESSION_URL, exc=requests.exceptions.Timeout)
    _app, client = _app_and_client(conn)
    client.set_cookie(SESSION_COOKIE_NAME, "fake-session-token")
    resp = client.get("/alerts/register")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_gated_route_with_unauthenticated_get_session_redirects_to_login(conn, requests_mock):
    """Test /alerts/register (gated route) with no valid session redirects to login.
    Better Auth returns literal JSON null (not {} or {"user": null}) for no session."""
    requests_mock.get(GET_SESSION_URL, json=None)
    _app, client = _app_and_client(conn)
    client.set_cookie(SESSION_COOKIE_NAME, "fake-session-token")
    resp = client.get("/alerts/register")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_gated_route_without_telegram_redirects_to_verify(conn, requests_mock):
    """Test /alerts/register (gated route) without a linked Telegram redirects to /verify.
    telegramVerified is `null` until linked, not `false` -- confirm the login_required
    `and` check treats that correctly."""
    requests_mock.get(GET_SESSION_URL, json={"session": {}, "user": _user(telegram_verified=None)})
    _app, client = _app_and_client(conn)
    client.set_cookie(SESSION_COOKIE_NAME, "fake-session-token")
    resp = client.get("/alerts/register")
    assert resp.status_code == 302
    assert "/verify" in resp.headers["Location"]


def test_gated_route_with_unverified_email_redirects_to_verify(conn, requests_mock):
    """Test /alerts/register (gated route) with unverified email redirects to /verify."""
    requests_mock.get(GET_SESSION_URL, json={"session": {}, "user": _user(email_verified=False)})
    _app, client = _app_and_client(conn)
    client.set_cookie(SESSION_COOKIE_NAME, "fake-session-token")
    resp = client.get("/alerts/register")
    assert resp.status_code == 302
    assert "/verify" in resp.headers["Location"]


def test_login_page_renders_without_cookie_and_without_calling_auth_service(conn, requests_mock):
    _app, client = _app_and_client(conn)
    resp = client.get("/login")
    assert resp.status_code == 200
    assert requests_mock.call_count == 0


def test_register_page_renders(conn):
    _app, client = _app_and_client(conn)
    resp = client.get("/register")
    assert resp.status_code == 200


def test_verify_page_renders(conn):
    _app, client = _app_and_client(conn)
    resp = client.get("/verify")
    assert resp.status_code == 200


def test_logout_calls_sign_out_with_cookie_and_matching_origin_header(conn, requests_mock):
    # load_current_user's before_request also fires on /logout (the cookie is present),
    # so get-session needs a registered response too -- its result doesn't matter here.
    requests_mock.get(GET_SESSION_URL, json=None)
    requests_mock.post(SIGN_OUT_URL, json={"success": True})
    _app, client = _app_and_client(conn)
    client.set_cookie(SESSION_COOKIE_NAME, "fake-session-token")

    resp = client.post("/logout")

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
    sent = requests_mock.request_history[-1]
    assert sent.url == SIGN_OUT_URL
    assert sent.headers["Origin"] == config.WEB_ORIGIN
    assert SESSION_COOKIE_NAME in sent.headers.get("Cookie", "")


def test_logout_rejects_get(conn, requests_mock):
    """A GET logout can be fired by any third-party page's <img>/<script> tag, clearing a
    visitor's session without their involvement. It must not be reachable that way."""
    requests_mock.get(GET_SESSION_URL, json=None)
    sign_out = requests_mock.post(SIGN_OUT_URL, json={"success": True})
    _app, client = _app_and_client(conn)
    client.set_cookie(SESSION_COOKIE_NAME, "fake-session-token")

    resp = client.get("/logout")

    assert resp.status_code == 405
    # before_request still resolves a session on any request; what must not happen is
    # the sign-out itself.
    assert sign_out.call_count == 0


def test_logout_deletes_both_possible_cookie_names(conn, requests_mock):
    requests_mock.get(GET_SESSION_URL, json=None)
    requests_mock.post(SIGN_OUT_URL, json={"success": True})
    _app, client = _app_and_client(conn)
    client.set_cookie(SESSION_COOKIE_NAME, "fake-session-token")

    resp = client.post("/logout")

    set_cookie_headers = resp.headers.getlist("Set-Cookie")
    plain = next(h for h in set_cookie_headers if h.startswith("jobhub-auth.session_token="))
    secure_prefixed = next(h for h in set_cookie_headers if h.startswith("__Secure-jobhub-auth.session_token="))
    # The __Secure- prefix requires the deleting Set-Cookie to also carry Secure, or
    # browsers reject it outright and the cookie would silently fail to clear.
    assert "Secure" in secure_prefixed
    assert plain  # no such requirement for the unprefixed name


def test_logout_survives_auth_service_being_unreachable(conn, requests_mock, caplog):
    requests_mock.get(GET_SESSION_URL, json=None)
    requests_mock.post(SIGN_OUT_URL, exc=requests.exceptions.ConnectionError)
    _app, client = _app_and_client(conn)
    client.set_cookie(SESSION_COOKIE_NAME, "fake-session-token")

    resp = client.post("/logout")

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
    assert any(r.levelname == "WARNING" and "sign-out" in r.getMessage() for r in caplog.records)


def test_logout_warns_but_still_logs_out_client_side_on_non_2xx_sign_out(conn, requests_mock, caplog):
    """A non-2xx sign-out leaves the server-side session alive. The user must still end
    up looking logged out (cookies cleared, redirected) -- failing the other way would
    strand them logged in -- but the discrepancy must not pass silently."""
    requests_mock.get(GET_SESSION_URL, json=None)
    requests_mock.post(SIGN_OUT_URL, status_code=403, json={"code": "INVALID_ORIGIN"})
    _app, client = _app_and_client(conn)
    client.set_cookie(SESSION_COOKIE_NAME, "fake-session-token")

    resp = client.post("/logout")

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
    set_cookie_headers = resp.headers.getlist("Set-Cookie")
    assert any(h.startswith("jobhub-auth.session_token=") for h in set_cookie_headers)
    assert any(h.startswith("__Secure-jobhub-auth.session_token=") for h in set_cookie_headers)
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any("403" in r.getMessage() for r in warnings), caplog.text


@pytest.mark.parametrize("path", ["/login", "/register", "/verify"])
def test_auth_pages_carry_turnstile_sitekey_and_explicit_loader(conn, monkeypatch, path):
    monkeypatch.setattr(config, "TURNSTILE_SITEKEY", "sitekey-123")
    html = _app_and_client(conn)[1].get(path).get_data(as_text=True)
    assert '<meta name="turnstile-sitekey" content="sitekey-123">' in html
    assert 'id="turnstile-container"' in html
    assert "turnstile/v0/api.js?render=explicit" in html


def test_every_page_carries_the_jobshub_brand_and_favicons(conn):
    html = _app_and_client(conn)[1].get("/login").get_data(as_text=True)
    assert "<title>JobsHub</title>" in html
    assert ">JobsHub</span>" in html and "by aavartlabs" in html
    assert "/static/brand/mark-64.png" in html
    assert "/static/brand/favicon.ico" in html and "/static/brand/apple-touch-icon.png" in html
    assert "POC" not in html


def test_whatsapp_verified_account_without_telegram_must_link_it(conn, requests_mock):
    """Accounts verified by WhatsApp before the switch to Telegram go to /verify once."""
    user = {**_user(telegram_verified=None), "phoneNumberVerified": True}
    requests_mock.get(GET_SESSION_URL, json={"session": {}, "user": user})
    _app, client = _app_and_client(conn)
    client.set_cookie(SESSION_COOKIE_NAME, "fake-session-token")
    assert "/verify" in client.get("/alerts").headers["Location"]
