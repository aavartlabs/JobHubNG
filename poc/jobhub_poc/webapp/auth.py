"""Owner identity, sourced from poc/auth-service/ (a standalone Better Auth companion
service), not from anything stored by this Flask app itself. There is no local
app_users table or Flask session anymore -- g.current_user is populated fresh on every
request from the auth-service's own session cookie, via load_current_user() below
(registered as app.before_request in app.py).
"""
import functools

import requests
from flask import Blueprint, g, redirect, render_template, request, url_for

from jobhub_poc import config

bp = Blueprint("auth", __name__)

# Better Auth prefixes the session cookie name with "__Secure-" whenever the connection
# is treated as secure (an https:// BETTER_AUTH_URL, or NODE_ENV=production) -- confirmed
# against the real installed library in Task 1 (see poc/auth-service/README.md). Production
# (jobhubs.aavartlabs.com) is https, so both names must be checked; don't hardcode one.
SESSION_COOKIE_NAMES = ("__Secure-jobhub-auth.session_token", "jobhub-auth.session_token")

_GET_SESSION_TIMEOUT_SECONDS = 5
_SIGN_OUT_TIMEOUT_SECONDS = 5


def load_current_user():
    """Registered as app.before_request. Sets g.current_user unconditionally on every
    request. Makes zero outbound HTTP calls when neither possible session cookie name is
    present on the request. When one is present, calls the auth-service's
    GET /auth/get-session (forwarding the raw Cookie header) and sets g.current_user from
    the "user" key of a successful, non-null response. Fails open to anonymous (None) on
    any error, timeout, non-2xx response, or an unauthenticated ("null") response -- a
    broken auth-service must only cost us gated access, never lock everyone in or crash
    the request.
    """
    g.current_user = None

    if not any(name in request.cookies for name in SESSION_COOKIE_NAMES):
        return

    try:
        resp = requests.get(
            f"{config.AUTH_SERVICE_URL}/auth/get-session",
            headers={"Cookie": request.headers.get("Cookie", "")},
            timeout=_GET_SESSION_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return

    if data:
        g.current_user = data.get("user")


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        user = getattr(g, "current_user", None)
        if user is None:
            return redirect(url_for("auth.login"))
        # phoneNumberVerified is `null` (not `false`) before phone verification --
        # Python's `and` already treats None as falsy here, no special-casing needed.
        if not (user.get("emailVerified") and user.get("phoneNumberVerified")):
            return redirect(url_for("auth.verify"))
        return view(*args, **kwargs)
    return wrapped


@bp.route("/login")
def login():
    """Thin shell -- the actual POST /auth/sign-in/email call is made client-side (see
    frontend/src/auth.ts) via fetch against the /auth/* proxy, since Better Auth speaks
    JSON, not form-encoded bodies, and auth_proxy.py is a byte-level passthrough that
    doesn't reshape request bodies."""
    return render_template("login.html")


@bp.route("/register")
def register():
    """Thin shell -- sign-up + both OTP sends happen client-side, see auth.ts."""
    return render_template("register.html")


@bp.route("/verify")
def verify():
    """Thin shell -- both OTP verify calls (and the email resend affordance) happen
    client-side, see auth.ts."""
    return render_template("verify.html")


@bp.route("/logout")
def logout():
    # Server-to-server call, not browser-initiated -- Better Auth's CSRF check requires
    # an explicit Origin header matching the auth-service's TRUSTED_ORIGINS on any POST
    # that carries the session cookie (confirmed in Task 1; auth_proxy.py's passthrough
    # doesn't need this since it forwards the browser's own Origin header already).
    try:
        requests.post(
            f"{config.AUTH_SERVICE_URL}/auth/sign-out",
            headers={
                "Cookie": request.headers.get("Cookie", ""),
                "Origin": config.WEB_ORIGIN,
            },
            timeout=_SIGN_OUT_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        pass  # best-effort -- still clear the cookie client-side and send them to login

    response = redirect(url_for("auth.login"))
    # A `__Secure-`-prefixed cookie name requires the Set-Cookie that clears it to also
    # carry the Secure attribute, or browsers reject that Set-Cookie outright (the
    # prefix's own enforcement rule) and the cookie would silently fail to clear.
    # delete_cookie()'s default (secure=False) is correct for the plain name.
    response.delete_cookie("__Secure-jobhub-auth.session_token", secure=True)
    response.delete_cookie("jobhub-auth.session_token")
    return response
