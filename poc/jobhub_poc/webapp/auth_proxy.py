"""Byte-level passthrough for everything under /auth/* to poc/auth-service/'s own
Better Auth router. Exists because the browser only ever talks to this Flask app on one
public origin -- the auth-service itself is never exposed to the host (see
docker-compose.yml) -- and because Better Auth's CSRF check validates the browser's own
Origin header, which this passthrough forwards unchanged rather than reconstructing.

This does not parse or reshape request/response bodies at all: Better Auth speaks JSON,
this just relays whatever bytes came in and whatever bytes come back, including
Set-Cookie (so sign-in/sign-up/sign-out cookies reach the browser as if talking to
Better Auth directly).
"""
import requests
from flask import Blueprint, Response, jsonify, request

from jobhub_poc import config
from jobhub_poc.webapp import turnstile
from jobhub_poc.webapp.auth import client_ip

bp = Blueprint("auth_proxy", __name__)

# Headers that are specific to a single hop and must not be relayed verbatim in either
# direction (RFC 2616 sec. 13.5.1's hop-by-hop set, plus Content-Length/Content-Encoding
# since the relayed body's actual length/encoding can differ from the original -- Flask
# and `requests` each recompute these correctly on their own).
_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-encoding",
    "content-length",
}
# Must outlast the slowest upstream call: /auth/phone-number/send-otp blocks until
# whatsapp-sender gets a WhatsApp server ack, which it waits up to ACK_TIMEOUT_MS=45000
# for (poc/whatsapp-sender/.env). Must also stay under Cloudflare's 100s origin timeout.
_PROXY_TIMEOUT_SECONDS = 60

# Forwarding headers a caller can set themselves. The auth-service rate-limits by client
# IP (see poc/auth-service/src/auth.js) and reads that IP from X-Forwarded-For, so
# relaying an inbound one verbatim would let any caller mint a fresh rate-limit bucket
# per request -- on endpoints (/phone-number/send-otp, /email-otp/send-verification-otp)
# that need no authentication and trigger a real WhatsApp or email send to an
# attacker-chosen recipient. Dropped here and replaced with one value this app derives
# itself; see auth.client_ip() for where that value comes from.
_CLIENT_CONTROLLED_FORWARDING_HEADERS = {
    "x-forwarded-for",
    "x-real-ip",
    "forwarded",
}


# Every Better Auth endpoint that sends a real email/WhatsApp message to a caller-chosen
# recipient, or checks a password, mapped to the Turnstile action its token must carry.
# Includes endpoints the frontend never calls (password reset, OTP/phone sign-in): they
# are still reachable through this proxy, so they must not be the unguarded way in.
_TURNSTILE_ACTIONS = {
    "sign-up/email": "signup",
    "sign-in/email": "login",
    "sign-in/phone-number": "login",
    "sign-in/email-otp": "login",
    "email-otp/send-verification-otp": "send_email_otp",
    "forget-password/email-otp": "send_email_otp",
    "email-otp/request-password-reset": "send_email_otp",
    "email-otp/request-email-change": "send_email_otp",
    "phone-number/send-otp": "send_phone_otp",
    "phone-number/request-password-reset": "send_phone_otp",
}
# Sent by frontend/src/auth.ts on each protected call; consumed here, never forwarded.
TURNSTILE_HEADER = "X-Turnstile-Token"
# auth-service's /internal/admin/* key. Only admin.py sends it, server-side; a caller
# supplying one through this proxy is never legitimate.
_NEVER_FORWARDED_HEADERS = {TURNSTILE_HEADER.lower(), "x-admin-api-key"}


def _is_clean(subpath):
    """No "." / ".." / empty segments and no backslashes. requests/urllib3 resolves dot
    segments before sending, so "sign-up/./email" would miss _TURNSTILE_ACTIONS yet reach
    /auth/sign-up/email upstream, and "../internal/admin/users" would escape /auth/
    altogether onto auth-service's internal admin API. Refused rather than normalised:
    no legitimate client sends these."""
    return "\\" not in subpath and all(part not in ("", ".", "..") for part in subpath.split("/"))


def _turnstile_action(subpath):
    # Lower-cased so "SIGN-UP/email" can't slip past as a different key.
    return _TURNSTILE_ACTIONS.get(subpath.lower())


@bp.route("/auth/<path:subpath>", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
def proxy(subpath):
    if not _is_clean(subpath):
        return jsonify({"code": "BAD_PATH", "message": "Invalid path."}), 400

    action = _turnstile_action(subpath) if request.method not in ("GET", "HEAD", "OPTIONS") else None
    if action and not turnstile.verify(request.headers.get(TURNSTILE_HEADER), action):
        return jsonify({
            "code": "TURNSTILE_FAILED",
            "message": "Bot check failed or expired. Please try again.",
        }), 403

    outbound_headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in _HOP_BY_HOP_HEADERS
        and key.lower() not in _CLIENT_CONTROLLED_FORWARDING_HEADERS
        and key.lower() != "host"
        and key.lower() not in _NEVER_FORWARDED_HEADERS
    }
    # Exactly one value, never appended to an inbound chain: Better Auth only trusts a
    # single-valued X-Forwarded-For (a comma-separated chain makes it fall back to one
    # shared bucket for everyone) -- confirmed in
    # node_modules/@better-auth/core/dist/utils/ip.mjs's getIPFromHeader.
    outbound_headers["X-Forwarded-For"] = client_ip()

    try:
        upstream = requests.request(
            method=request.method,
            url=f"{config.AUTH_SERVICE_URL}/auth/{subpath}",
            headers=outbound_headers,
            params=request.args,
            data=request.get_data(),
            timeout=_PROXY_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        return jsonify({"error": f"auth-service unreachable: {exc}"}), 502

    # upstream.raw.headers (a urllib3 HTTPHeaderDict) preserves repeated header names --
    # unlike upstream.headers, which comma-joins duplicates and would corrupt multiple
    # Set-Cookie headers into one unparseable value.
    response_headers = [
        (key, value)
        for key, value in upstream.raw.headers.items()
        if key.lower() not in _HOP_BY_HOP_HEADERS
    ]
    return Response(upstream.content, status=upstream.status_code, headers=response_headers)
