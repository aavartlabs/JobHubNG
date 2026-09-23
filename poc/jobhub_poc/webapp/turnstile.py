"""Server-side Cloudflare Turnstile verification (canonical siteverify), shared by every
protected handler: auth_proxy.py (signup/login/OTP sends), routes_alerts.py (alert
registration) and admin.py (admin login).

Always browser -> this app -> siteverify, never from the browser. Fails closed: no
secret, no token, a network error, or any mismatch is a rejection, never a pass.
"""
import requests
from flask import current_app

from jobhub_poc import config
from jobhub_poc.webapp.auth import client_ip

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
_TIMEOUT_SECONDS = 10
_MAX_TOKEN_LENGTH = 2048


def verify(token, action):
    """True only if Cloudflare says `token` is valid, was issued for `action`, and was
    solved on one of config.TURNSTILE_HOSTNAMES. Tokens are single-use, so each call
    needs a fresh one."""
    if not config.CF_TURNSTILE_SECRET or not config.TURNSTILE_HOSTNAMES:
        current_app.logger.error("turnstile: CF_TURNSTILE_SECRET or TURNSTILE_HOSTNAMES unset; rejecting")
        return False
    if not isinstance(token, str) or not token or len(token) > _MAX_TOKEN_LENGTH:
        return False

    try:
        resp = requests.post(
            SITEVERIFY_URL,
            data={"secret": config.CF_TURNSTILE_SECRET, "response": token, "remoteip": client_ip()},
            timeout=_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        result = resp.json()
    except (requests.RequestException, ValueError) as exc:
        current_app.logger.warning("turnstile: siteverify call failed: %s", exc)
        return False

    if not result.get("success"):
        current_app.logger.info("turnstile: rejected (%s): %s", action, result.get("error-codes"))
        return False

    # Cloudflare's published test secret (for local dev) always succeeds, reports
    # hostname example.com and no action -- only acceptable when explicitly enabled.
    if (result.get("metadata") or {}).get("result_with_testing_key"):
        return bool(config.TURNSTILE_ALLOW_TEST_KEYS)

    if result.get("action") != action or result.get("hostname") not in config.TURNSTILE_HOSTNAMES:
        current_app.logger.warning(
            "turnstile: action/hostname mismatch: wanted %s on %s, got %s on %s",
            action, sorted(config.TURNSTILE_HOSTNAMES), result.get("action"), result.get("hostname"),
        )
        return False
    return True
