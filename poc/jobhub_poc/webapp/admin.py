"""Admin console: sign in as an app_users row, then list, edit, sign out or delete the
site's registered users.

Identity is separate from site users on purpose. Site users live in auth-service's
auth.db and sign in through Better Auth; the admin is an app_users row in jobhub.db with
its own Flask session cookie (see app.py's SESSION_COOKIE_NAME). Being an admin never
makes you a site user, and vice versa. User records are read and changed through
auth-service's internal API (auth-service/src/admin.js), since Flask can't reach auth.db
directly.

Brute-force protection on /admin/login: Turnstile first, then a lockout keyed on both
the client IP and the username. After ADMIN_MAX_FAILURES failures a key is locked for
ADMIN_LOCKOUT_MINUTES, doubling on each further lockout up to ADMIN_LOCKOUT_MAX_MINUTES.
A locked key is refused before the password is even checked.
"""
import functools
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from jobhub_poc import auth_admin_client, config
from jobhub_poc.auth_admin_client import AuthServiceError
from jobhub_poc.phone import normalize_e164
from jobhub_poc.webapp import turnstile
from jobhub_poc.webapp.auth import client_ip

bp = Blueprint("admin", __name__, url_prefix="/admin")

# Compared against when the username doesn't exist, so a miss costs as much time as a
# wrong password and response timing doesn't reveal which usernames are real.
_DUMMY_HASH = generate_password_hash("not-a-real-password")


# ---- session + CSRF ----

def is_admin():
    return "admin_user_id" in session


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def _check_csrf():
    sent = request.form.get("csrf_token", "")
    if not sent or not hmac.compare_digest(sent, session.get("csrf_token", "")):
        abort(400, "Missing or invalid CSRF token")


def admin_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not is_admin():
            return redirect(url_for("admin.login"))
        if request.method == "POST":
            _check_csrf()
        return view(*args, **kwargs)
    return wrapped


# ---- lockout ----

def _now():
    return datetime.now(timezone.utc)


def _lock_remaining(conn, keys):
    """Longest remaining lock across `keys`, or None if none is locked."""
    now = _now()
    remaining = []
    for row in conn.execute(
        f"SELECT locked_until FROM admin_login_attempts WHERE key IN ({','.join('?' * len(keys))})", keys
    ):
        if row["locked_until"]:
            until = datetime.fromisoformat(row["locked_until"])
            if until > now:
                remaining.append(until - now)
    return max(remaining) if remaining else None


def _record_failure(conn, key):
    row = conn.execute("SELECT * FROM admin_login_attempts WHERE key = ?", (key,)).fetchone()
    failures = (row["failures"] if row else 0) + 1
    lock_count = row["lock_count"] if row else 0
    locked_until = row["locked_until"] if row else None
    if failures >= config.ADMIN_MAX_FAILURES:
        lock_count += 1
        minutes = min(config.ADMIN_LOCKOUT_MINUTES * 2 ** (lock_count - 1), config.ADMIN_LOCKOUT_MAX_MINUTES)
        locked_until = (_now() + timedelta(minutes=minutes)).isoformat()
        failures = 0
        current_app.logger.warning("admin login: locked %s for %d minutes", key, minutes)
    conn.execute(
        """
        INSERT INTO admin_login_attempts (key, failures, lock_count, locked_until, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET failures = excluded.failures, lock_count = excluded.lock_count,
            locked_until = excluded.locked_until, updated_at = excluded.updated_at
        """,
        (key, failures, lock_count, locked_until, _now().isoformat()),
    )


# ---- auth-service internal API ----

def _api(method, path="", json=None):
    return auth_admin_client.call(method, path, json)


def _find_user(user_id):
    user = next((u for u in _api("GET")["users"] if u["id"] == user_id), None)
    if user is None:
        abort(404)
    return user


@bp.errorhandler(AuthServiceError)
def _auth_service_error(exc):
    current_app.logger.error("admin: %s", exc)
    return render_template("admin_error.html", message=str(exc)), 502 if exc.status >= 500 else exc.status


# ---- routes ----

@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("admin_login.html")

    conn = current_app.get_db()
    username = request.form.get("username", "").strip()
    ip = client_ip()
    keys = [f"ip:{ip}", f"user:{username.lower()}"]

    remaining = _lock_remaining(conn, keys)
    if remaining is not None:
        minutes = int(remaining.total_seconds() // 60) + 1
        current_app.logger.warning("admin login: refused while locked (user=%r ip=%s)", username, ip)
        return render_template(
            "admin_login.html", error=f"Too many failed attempts. Try again in {minutes} minutes."
        ), 429

    if not turnstile.verify(request.form.get("cf-turnstile-response"), "admin_login"):
        return render_template("admin_login.html", error="Bot check failed or expired. Please try again."), 403

    row = conn.execute("SELECT * FROM app_users WHERE username = ?", (username,)).fetchone()
    password = request.form.get("password", "")
    valid = check_password_hash(row["password_hash"] if row else _DUMMY_HASH, password) and row is not None
    if not valid:
        for key in keys:
            _record_failure(conn, key)
        conn.commit()
        current_app.logger.warning("admin login: failed (user=%r ip=%s)", username, ip)
        return render_template("admin_login.html", error="Invalid username or password."), 401

    conn.execute(
        f"DELETE FROM admin_login_attempts WHERE key IN ({','.join('?' * len(keys))})", keys
    )
    conn.commit()
    session.clear()  # no fixation: a fresh session, and a fresh CSRF token with it
    session.permanent = True
    session["admin_user_id"] = row["id"]
    session["admin_username"] = row["username"]
    current_app.logger.info("admin login: success (user=%r ip=%s)", username, ip)
    return redirect(url_for("admin.users"))


@bp.route("/logout", methods=["POST"])
@admin_required
def logout():
    session.clear()
    return redirect(url_for("admin.login"))


@bp.route("")
@admin_required
def index():
    return redirect(url_for("admin.users"))


@bp.route("/users")
@admin_required
def users():
    user_list = _api("GET")["users"]
    counts = {
        row["owner_auth_user_id"]: row
        for row in current_app.get_db().execute(
            """
            SELECT owner_auth_user_id, SUM(is_active) AS active, COUNT(*) AS total
            FROM alert_subscriptions WHERE owner_auth_user_id IS NOT NULL GROUP BY owner_auth_user_id
            """
        )
    }
    for user in user_list:
        row = counts.get(user["id"])
        user["subscriptions"] = f"{row['active'] if row else 0} active / {row['total'] if row else 0}"
    return render_template("admin_users.html", users=user_list)


@bp.route("/users/<user_id>", methods=["GET", "POST"])
@admin_required
def edit_user(user_id):
    user = _find_user(user_id)
    if request.method == "GET":
        return render_template("admin_user_edit.html", user=user)

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    raw_phone = request.form.get("phone_number", "").strip()
    phone = normalize_e164(raw_phone) if raw_phone else ""
    if phone is None:
        flash("Not saved: mobile must be + and the country code, e.g. +91 98765 43210.")
        return redirect(url_for("admin.edit_user", user_id=user_id))
    email_verified = request.form.get("email_verified") == "on"
    phone_verified = request.form.get("phone_verified") == "on"

    changes = {}
    if name != user["name"]:
        changes["name"] = name
    if email != user["email"]:
        # A new address hasn't been proven by anyone, whatever the checkbox says.
        changes["email"] = email
        email_verified = False
    if phone != (user.get("phoneNumber") or ""):
        changes["phoneNumber"] = phone
        phone_verified = False
    if email_verified != bool(user["emailVerified"]):
        changes["emailVerified"] = email_verified
    if phone_verified != bool(user["phoneNumberVerified"]):
        changes["phoneNumberVerified"] = phone_verified

    if not changes:
        flash("No changes.")
        return redirect(url_for("admin.edit_user", user_id=user_id))
    try:
        _api("PATCH", f"/{user_id}", json=changes)
    except AuthServiceError as exc:
        if exc.status >= 500:
            raise
        flash(f"Not saved: {exc}")
        return redirect(url_for("admin.edit_user", user_id=user_id))
    current_app.logger.info("admin %s updated user %s: %s", session["admin_username"], user_id, sorted(changes))
    flash("Saved.")
    return redirect(url_for("admin.edit_user", user_id=user_id))


@bp.route("/users/<user_id>/revoke-sessions", methods=["POST"])
@admin_required
def revoke_sessions(user_id):
    revoked = _api("POST", f"/{user_id}/revoke-sessions")["revoked"]
    current_app.logger.info("admin %s revoked %d sessions of %s", session["admin_username"], revoked, user_id)
    flash(f"Signed out {revoked} session(s).")
    return redirect(url_for("admin.edit_user", user_id=user_id))


@bp.route("/users/<user_id>/delete", methods=["GET", "POST"])
@admin_required
def delete_user(user_id):
    if request.method == "GET":
        return render_template("admin_user_delete.html", user=_find_user(user_id))

    # auth-service first: if it fails, the user still exists and so should their alerts.
    _api("DELETE", f"/{user_id}")
    conn = current_app.get_db()
    conn.execute(
        "DELETE FROM alerts_sent WHERE subscription_id IN "
        "(SELECT id FROM alert_subscriptions WHERE owner_auth_user_id = ?)",
        (user_id,),
    )
    conn.execute("DELETE FROM alert_subscriptions WHERE owner_auth_user_id = ?", (user_id,))
    conn.execute("DELETE FROM job_interactions WHERE owner_auth_user_id = ?", (user_id,))
    conn.commit()
    current_app.logger.info("admin %s deleted user %s", session["admin_username"], user_id)
    flash("User deleted.")
    return redirect(url_for("admin.users"))
