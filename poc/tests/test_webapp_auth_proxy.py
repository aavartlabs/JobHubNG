import json

import pytest

import requests

from jobhub_poc import config
from jobhub_poc.webapp.app import create_app


def _client(conn):
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    return app.test_client()


def test_proxy_forwards_get_and_relays_json_body(conn, requests_mock):
    requests_mock.get(
        f"{config.AUTH_SERVICE_URL}/auth/get-session",
        json={"session": {"id": "s1"}, "user": {"id": "u1", "email": "a@example.com"}},
    )
    client = _client(conn)

    resp = client.get("/auth/get-session")

    assert resp.status_code == 200
    assert json.loads(resp.data)["user"]["id"] == "u1"


def test_proxy_forwards_post_body_and_relays_set_cookie(conn, requests_mock, turnstile_calls):
    requests_mock.post(
        f"{config.AUTH_SERVICE_URL}/auth/sign-in/email",
        json={"token": "abc", "user": {"id": "u1"}},
        headers={"Set-Cookie": "jobhub-auth.session_token=abc123; Path=/; HttpOnly"},
    )
    client = _client(conn)

    resp = client.post(
        "/auth/sign-in/email",
        json={"email": "a@example.com", "password": "secret"},
        headers={"X-Turnstile-Token": "good-token"},
    )

    assert resp.status_code == 200
    sent = requests_mock.request_history[0]
    assert sent.json() == {"email": "a@example.com", "password": "secret"}
    assert "jobhub-auth.session_token=abc123" in resp.headers.get("Set-Cookie", "")


def test_proxy_forwards_query_params(conn, requests_mock):
    requests_mock.get(f"{config.AUTH_SERVICE_URL}/auth/some-path", json={"ok": True})
    client = _client(conn)

    client.get("/auth/some-path?foo=bar")

    sent = requests_mock.request_history[0]
    assert sent.qs.get("foo") == ["bar"]


def test_proxy_forwards_origin_header(conn, requests_mock):
    requests_mock.post(f"{config.AUTH_SERVICE_URL}/auth/sign-out", json={"success": True})
    client = _client(conn)

    client.post("/auth/sign-out", headers={"Origin": "https://jobhubs.aavartlabs.com"})

    sent = requests_mock.request_history[0]
    assert sent.headers["Origin"] == "https://jobhubs.aavartlabs.com"


def test_proxy_replaces_caller_supplied_forwarding_headers(conn, requests_mock, turnstile_calls):
    """The auth-service rate-limits by client IP read from X-Forwarded-For. Relaying a
    caller's own forwarding headers would hand them a fresh rate-limit bucket per
    request on endpoints that trigger real WhatsApp/email sends without authentication."""
    requests_mock.post(f"{config.AUTH_SERVICE_URL}/auth/phone-number/send-otp", json={"message": "code sent"})
    client = _client(conn)

    client.post(
        "/auth/phone-number/send-otp",
        json={"phoneNumber": "+15551234567"},
        headers={
            "X-Forwarded-For": "6.6.6.6",
            "X-Real-IP": "6.6.6.6",
            "Forwarded": "for=6.6.6.6",
            "X-Turnstile-Token": "good-token",
        },
        environ_base={"REMOTE_ADDR": "203.0.113.9"},
    )

    sent = requests_mock.request_history[0]
    assert sent.headers["X-Forwarded-For"] == "203.0.113.9"
    assert "X-Real-IP" not in sent.headers
    assert "Forwarded" not in sent.headers


def test_proxy_uses_cloudflares_real_client_ip_when_present(conn, requests_mock, turnstile_calls):
    """Behind the Cloudflare Tunnel, remote_addr is cloudflared's own address -- the same
    for every visitor. CF-Connecting-IP is the real client, and it wins when set."""
    requests_mock.post(f"{config.AUTH_SERVICE_URL}/auth/phone-number/send-otp", json={"message": "code sent"})
    client = _client(conn)

    client.post(
        "/auth/phone-number/send-otp",
        json={"phoneNumber": "+15551234567"},
        headers={
            "CF-Connecting-IP": "198.51.100.7",
            "X-Forwarded-For": "6.6.6.6",
            "X-Turnstile-Token": "good-token",
        },
        environ_base={"REMOTE_ADDR": "172.18.0.4"},
    )

    sent = requests_mock.request_history[0]
    assert sent.headers["X-Forwarded-For"] == "198.51.100.7"


def test_proxy_relays_non_2xx_status_code(conn, requests_mock, turnstile_calls):
    requests_mock.post(
        f"{config.AUTH_SERVICE_URL}/auth/sign-in/email",
        status_code=403,
        json={"code": "EMAIL_AND_PHONE_VERIFICATION_REQUIRED"},
    )
    client = _client(conn)

    resp = client.post(
        "/auth/sign-in/email",
        json={"email": "a@example.com", "password": "secret"},
        headers={"X-Turnstile-Token": "good-token"},
    )

    assert resp.status_code == 403
    assert json.loads(resp.data)["code"] == "EMAIL_AND_PHONE_VERIFICATION_REQUIRED"


def test_proxy_does_not_also_resolve_a_session_via_before_request(conn, requests_mock):
    """load_current_user runs on every request, but /auth/* never reads g.current_user --
    resolving one here would be a second, wasted get-session round trip on top of the
    proxied call itself. Exactly one outbound call, and it's the proxied one."""
    requests_mock.post(f"{config.AUTH_SERVICE_URL}/auth/sign-out", json={"success": True})
    client = _client(conn)
    client.set_cookie("jobhub-auth.session_token", "fake-session-token")

    client.post("/auth/sign-out")

    assert requests_mock.call_count == 1
    assert requests_mock.request_history[0].path == "/auth/sign-out"


def test_proxy_connection_error_returns_502_json(conn, requests_mock):
    requests_mock.get(
        f"{config.AUTH_SERVICE_URL}/auth/get-session",
        exc=requests.exceptions.ConnectionError,
    )
    client = _client(conn)

    resp = client.get("/auth/get-session")

    assert resp.status_code == 502
    assert resp.content_type.startswith("application/json")
    assert "error" in resp.get_json()


def test_proxy_timeout_outlasts_whatsapp_gateway_ack_wait(conn, requests_mock, turnstile_calls):
    # /auth/phone-number/send-otp blocks inside auth-service until whatsapp-sender gets a
    # WhatsApp server ack, which it waits up to ACK_TIMEOUT_MS=45000 for. A shorter proxy
    # timeout 502s the browser while the OTP is still being (and often successfully) sent.
    requests_mock.post(
        f"{config.AUTH_SERVICE_URL}/auth/phone-number/send-otp",
        json={"status": True},
    )
    client = _client(conn)

    client.post(
        "/auth/phone-number/send-otp",
        json={"phoneNumber": "+15551234567"},
        headers={"X-Turnstile-Token": "good-token"},
    )

    assert requests_mock.last_request.timeout > 45


@pytest.mark.parametrize("path,action", [
    ("sign-up/email", "signup"),
    ("sign-in/email", "login"),
    ("sign-in/phone-number", "login"),
    ("sign-in/email-otp", "login"),
    ("email-otp/send-verification-otp", "send_email_otp"),
    ("forget-password/email-otp", "send_email_otp"),
    ("email-otp/request-password-reset", "send_email_otp"),
    ("phone-number/send-otp", "send_phone_otp"),
    ("phone-number/request-password-reset", "send_phone_otp"),
])
def test_protected_posts_need_a_turnstile_token_for_their_action(conn, requests_mock, turnstile_calls, path, action):
    upstream = requests_mock.post(f"{config.AUTH_SERVICE_URL}/auth/{path}", json={"ok": True})
    client = _client(conn)

    missing = client.post(f"/auth/{path}", json={})
    bad = client.post(f"/auth/{path}", json={}, headers={"X-Turnstile-Token": "forged"})
    good = client.post(f"/auth/{path}", json={}, headers={"X-Turnstile-Token": "good-token"})

    assert missing.status_code == 403
    assert missing.get_json()["code"] == "TURNSTILE_FAILED"
    assert bad.status_code == 403
    assert good.status_code == 200
    assert upstream.call_count == 1
    assert turnstile_calls[-1] == ("good-token", action)


def test_turnstile_token_is_not_forwarded_upstream(conn, requests_mock, turnstile_calls):
    requests_mock.post(f"{config.AUTH_SERVICE_URL}/auth/sign-up/email", json={"ok": True})
    client = _client(conn)

    client.post("/auth/sign-up/email", json={}, headers={"X-Turnstile-Token": "good-token"})

    assert "X-Turnstile-Token" not in requests_mock.last_request.headers


def test_unprotected_paths_need_no_token(conn, requests_mock, turnstile_calls):
    requests_mock.get(f"{config.AUTH_SERVICE_URL}/auth/get-session", json=None)
    requests_mock.post(f"{config.AUTH_SERVICE_URL}/auth/email-otp/verify-email", json={"ok": True})
    client = _client(conn)

    assert client.get("/auth/get-session").status_code == 200
    assert client.post("/auth/email-otp/verify-email", json={}).status_code == 200
    assert turnstile_calls == []


def test_protection_ignores_path_case_and_trailing_slash_tricks(conn, requests_mock, turnstile_calls):
    requests_mock.post(f"{config.AUTH_SERVICE_URL}/auth/sign-up/email/", json={"ok": True})
    requests_mock.post(f"{config.AUTH_SERVICE_URL}/auth/SIGN-UP/email", json={"ok": True})
    client = _client(conn)

    # Trailing slash: refused outright as a malformed path (400); odd case: bot-checked (403).
    assert client.post("/auth/sign-up/email/", json={}).status_code == 400
    assert client.post("/auth/SIGN-UP/email", json={}).status_code == 403
    assert requests_mock.call_count == 0


@pytest.mark.parametrize("path", [
    "/auth/sign-up/./email",
    "/auth/./sign-in/email",
    "/auth/phone-number/x/../send-otp",
    "/auth/../internal/admin/users",
    "/auth/%2e%2e/internal/admin/users",
    "/auth/sign-up//email",
    "/auth/sign-up\\email",
])
def test_dot_segments_and_odd_separators_are_refused_not_forwarded(conn, requests_mock, turnstile_calls, path):
    """requests/urllib3 resolves ./.. before sending, so a path that doesn't literally
    match _TURNSTILE_ACTIONS could still land on a protected endpoint -- or escape /auth/
    entirely onto auth-service's /internal/admin/* API."""
    client = _client(conn)
    for method in ("GET", "POST"):
        resp = client.open(path, method=method, json={}, headers={"X-Turnstile-Token": "good-token"})
        assert resp.status_code in (400, 404)
    assert requests_mock.call_count == 0


def test_admin_api_key_header_is_never_forwarded(conn, requests_mock):
    requests_mock.get(f"{config.AUTH_SERVICE_URL}/auth/get-session", json=None)
    _client(conn).get("/auth/get-session", headers={"X-Admin-Api-Key": "guessed"})
    assert "x-admin-api-key" not in {k.lower() for k in requests_mock.last_request.headers}


def test_request_email_change_is_turnstile_gated(conn, requests_mock, turnstile_calls):
    requests_mock.post(f"{config.AUTH_SERVICE_URL}/auth/email-otp/request-email-change", json={"ok": True})
    client = _client(conn)
    assert client.post("/auth/email-otp/request-email-change", json={}).status_code == 403
    assert client.post(
        "/auth/email-otp/request-email-change", json={}, headers={"X-Turnstile-Token": "good-token"}
    ).status_code == 200
    assert turnstile_calls[-1] == ("good-token", "send_email_otp")
