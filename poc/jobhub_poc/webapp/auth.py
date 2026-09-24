"""Owner identity, sourced from poc/auth-service/ (a standalone Better Auth companion
service), not from anything stored by this Flask app itself -- g.current_user is
populated fresh on every request from the auth-service's own session cookie, via
load_current_user() below (registered as app.before_request in app.py). The app_users
table and Flask's own session cookie belong only to the admin console (admin.py) and
never make anyone a site user.
"""
import functools
from urllib.parse import quote

import requests
from flask import Blueprint, current_app, g, redirect, render_template, request, url_for

from jobhub_poc import config

bp = Blueprint("auth", __name__)

# Better Auth prefixes the session cookie name with "__Secure-" whenever it treats the
# connection as secure, which with BETTER_AUTH_URL set (always, see that service's
# .env.example) follows that URL's scheme and NOT NODE_ENV -- confirmed by running the
# real service both ways (see poc/auth-service/README.md). Production
# (jobshub.aavartlabs.com) is https, local dev is http, so both names must be checked;
# don't hardcode one.
SESSION_COOKIE_NAMES = ("__Secure-jobhub-auth.session_token", "jobhub-auth.session_token")

_GET_SESSION_TIMEOUT_SECONDS = 5
_SIGN_OUT_TIMEOUT_SECONDS = 5


def client_ip():
    """The real end-user IP, as best this app can know it, for use as the auth-service's
    rate-limit key (Better Auth buckets by client IP + path; see poc/auth-service/src/auth.js).

    Every request that reaches the production deployment arrives through the Cloudflare
    Tunnel, whose ingress is fixed to jobhub-web:3000 -- so `request.remote_addr` is the
    cloudflared container's address, identical for every visitor, and using it would put
    the whole internet in one rate-limit bucket. Cloudflare sets `CF-Connecting-IP` to the
    real client address on every request it proxies, so that is the value to use when
    present, falling back to remote_addr for local/non-tunnel runs.

    Caveat, deliberately accepted: `web` also publishes port 8100 on pi09's host, so
    someone already on that LAN could reach Flask directly and spoof CF-Connecting-IP to
    get themselves a fresh bucket. That is a strictly smaller exposure than today's (any
    internet caller can do it through the tunnel), and closing it properly means not
    publishing 8100 -- a deployment change, not a code one.
    """
    return request.headers.get("CF-Connecting-IP") or request.remote_addr or ""


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

    # /auth/* is a byte-level passthrough to the auth-service (auth_proxy.py) and never
    # reads g.current_user; resolving a session here would just be a second, wasted
    # get-session round trip on top of the one the proxied call already makes.
    if request.blueprint == "auth_proxy":
        return

    if not any(name in request.cookies for name in SESSION_COOKIE_NAMES):
        return

    try:
        resp = requests.get(
            f"{config.AUTH_SERVICE_URL}/auth/get-session",
            headers={
                "Cookie": request.headers.get("Cookie", ""),
                # This is a server-to-server call, so without this the auth-service sees
                # no client IP at all and buckets every user of the site together under
                # one shared rate-limit key. See client_ip().
                "X-Forwarded-For": client_ip(),
            },
            timeout=_GET_SESSION_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return

    if data:
        g.current_user = data.get("user")


def login_url(next_path):
    """/login?next=<next_path>. The frontend re-validates `next` before following it
    (frontend/src/nav.ts safeNext), so only same-origin paths are ever honoured."""
    return f"{url_for('auth.login')}?next={quote(next_path, safe='/?')}"


def verify_url(next_path):
    return f"{url_for('auth.verify')}?next={quote(next_path, safe='/?')}"


def access_state():
    """"anonymous", "unverified" or "verified" for the current request's user."""
    user = getattr(g, "current_user", None)
    if user is None:
        return "anonymous"
    # A verified email is all an account needs. Telegram is optional: linking it only
    # unlocks Telegram alerts (routes_alerts.py checks telegramVerified for those).
    if not user.get("emailVerified"):
        return "unverified"
    return "verified"


def _current_path():
    query = request.query_string.decode()
    return f"{request.path}?{query}" if query else request.path


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        state = access_state()
        if state == "anonymous":
            return redirect(login_url(_current_path()))
        if state == "unverified":
            return redirect(verify_url(_current_path()))
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
    """Thin shell -- sign-up and the email-code send happen client-side, see auth.ts."""
    return render_template("register.html")


@bp.route("/verify")
def verify():
    """Thin shell -- the email code, the Telegram link and its code all happen
    client-side, see auth.ts."""
    return render_template("verify.html")


@bp.route("/logout", methods=["POST"])
def logout():
    """POST-only on purpose: a GET route that destroys a session can be fired by any
    third-party page with an <img>/<script> tag pointing at it. The nav's Logout is a
    small form (see templates/base.html) rather than a link for that reason."""
    # Server-to-server call, not browser-initiated -- Better Auth's CSRF check requires
    # an explicit Origin header matching the auth-service's TRUSTED_ORIGINS on any POST
    # that carries the session cookie (confirmed in Task 1; auth_proxy.py's passthrough
    # doesn't need this since it forwards the browser's own Origin header already).
    try:
        signed_out = requests.post(
            f"{config.AUTH_SERVICE_URL}/auth/sign-out",
            headers={
                "Cookie": request.headers.get("Cookie", ""),
                "Origin": config.WEB_ORIGIN,
                "X-Forwarded-For": client_ip(),
            },
            timeout=_SIGN_OUT_TIMEOUT_SECONDS,
        )
        if not signed_out.ok:
            # The server-side session is still alive even though the browser is about to
            # look logged out. Nothing useful to do for this user in the moment -- but it
            # must not vanish silently, because the failure mode (sessions that outlive
            # the logout that was meant to end them) is invisible otherwise.
            current_app.logger.warning(
                "auth-service sign-out returned %s; server-side session may still be active",
                signed_out.status_code,
            )
    except requests.RequestException as exc:
        # Best-effort -- still clear the cookie client-side and send them to login.
        current_app.logger.warning("auth-service sign-out call failed: %s", exc)

    response = redirect(url_for("auth.login"))
    # A `__Secure-`-prefixed cookie name requires the Set-Cookie that clears it to also
    # carry the Secure attribute, or browsers reject that Set-Cookie outright (the
    # prefix's own enforcement rule) and the cookie would silently fail to clear.
    # delete_cookie()'s default (secure=False) is correct for the plain name.
    response.delete_cookie("__Secure-jobhub-auth.session_token", secure=True)
    response.delete_cookie("jobhub-auth.session_token")
    return response
