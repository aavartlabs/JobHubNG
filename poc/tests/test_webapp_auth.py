import requests

from jobhub_poc import config
from jobhub_poc.webapp.app import create_app

SESSION_COOKIE_NAME = "jobhub-auth.session_token"
GET_SESSION_URL = f"{config.AUTH_SERVICE_URL}/auth/get-session"
SIGN_OUT_URL = f"{config.AUTH_SERVICE_URL}/auth/sign-out"


def _user(email_verified=True, phone_verified=True, user_id="auth-user-1"):
    return {
        "id": user_id,
        "email": "seeker@example.com",
        "name": "Job Seeker",
        "emailVerified": email_verified,
        # Better Auth's own default before phone verification is `null`, not `false` --
        # exercised directly below rather than always using bool.
        "phoneNumberVerified": phone_verified,
        "phoneNumber": "+15551234567",
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


def test_gated_route_with_unverified_phone_redirects_to_verify(conn, requests_mock):
    """Test /alerts/register (gated route) with unverified phone redirects to /verify.
    phoneNumberVerified is `null` before verification, not `false` -- confirm the
    login_required `and` check treats that correctly."""
    requests_mock.get(GET_SESSION_URL, json={"session": {}, "user": _user(phone_verified=None)})
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

    resp = client.get("/logout")

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
    sent = requests_mock.request_history[-1]
    assert sent.url == SIGN_OUT_URL
    assert sent.headers["Origin"] == config.WEB_ORIGIN
    assert SESSION_COOKIE_NAME in sent.headers.get("Cookie", "")


def test_logout_deletes_both_possible_cookie_names(conn, requests_mock):
    requests_mock.get(GET_SESSION_URL, json=None)
    requests_mock.post(SIGN_OUT_URL, json={"success": True})
    _app, client = _app_and_client(conn)
    client.set_cookie(SESSION_COOKIE_NAME, "fake-session-token")

    resp = client.get("/logout")

    set_cookie_headers = resp.headers.getlist("Set-Cookie")
    plain = next(h for h in set_cookie_headers if h.startswith("jobhub-auth.session_token="))
    secure_prefixed = next(h for h in set_cookie_headers if h.startswith("__Secure-jobhub-auth.session_token="))
    # The __Secure- prefix requires the deleting Set-Cookie to also carry Secure, or
    # browsers reject it outright and the cookie would silently fail to clear.
    assert "Secure" in secure_prefixed
    assert plain  # no such requirement for the unprefixed name


def test_logout_survives_auth_service_being_unreachable(conn, requests_mock):
    requests_mock.get(GET_SESSION_URL, json=None)
    requests_mock.post(SIGN_OUT_URL, exc=requests.exceptions.ConnectionError)
    _app, client = _app_and_client(conn)
    client.set_cookie(SESSION_COOKIE_NAME, "fake-session-token")

    resp = client.get("/logout")

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
