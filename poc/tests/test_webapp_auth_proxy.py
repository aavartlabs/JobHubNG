import json

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


def test_proxy_forwards_post_body_and_relays_set_cookie(conn, requests_mock):
    requests_mock.post(
        f"{config.AUTH_SERVICE_URL}/auth/sign-in/email",
        json={"token": "abc", "user": {"id": "u1"}},
        headers={"Set-Cookie": "jobhub-auth.session_token=abc123; Path=/; HttpOnly"},
    )
    client = _client(conn)

    resp = client.post("/auth/sign-in/email", json={"email": "a@example.com", "password": "secret"})

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


def test_proxy_replaces_caller_supplied_forwarding_headers(conn, requests_mock):
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
        },
        environ_base={"REMOTE_ADDR": "203.0.113.9"},
    )

    sent = requests_mock.request_history[0]
    assert sent.headers["X-Forwarded-For"] == "203.0.113.9"
    assert "X-Real-IP" not in sent.headers
    assert "Forwarded" not in sent.headers


def test_proxy_uses_cloudflares_real_client_ip_when_present(conn, requests_mock):
    """Behind the Cloudflare Tunnel, remote_addr is cloudflared's own address -- the same
    for every visitor. CF-Connecting-IP is the real client, and it wins when set."""
    requests_mock.post(f"{config.AUTH_SERVICE_URL}/auth/phone-number/send-otp", json={"message": "code sent"})
    client = _client(conn)

    client.post(
        "/auth/phone-number/send-otp",
        json={"phoneNumber": "+15551234567"},
        headers={"CF-Connecting-IP": "198.51.100.7", "X-Forwarded-For": "6.6.6.6"},
        environ_base={"REMOTE_ADDR": "172.18.0.4"},
    )

    sent = requests_mock.request_history[0]
    assert sent.headers["X-Forwarded-For"] == "198.51.100.7"


def test_proxy_relays_non_2xx_status_code(conn, requests_mock):
    requests_mock.post(
        f"{config.AUTH_SERVICE_URL}/auth/sign-in/email",
        status_code=403,
        json={"code": "EMAIL_AND_PHONE_VERIFICATION_REQUIRED"},
    )
    client = _client(conn)

    resp = client.post("/auth/sign-in/email", json={"email": "a@example.com", "password": "secret"})

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
