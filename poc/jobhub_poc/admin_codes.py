"""One-time codes for the admin console's second sign-in step (webapp/admin.py), shared
with the break-glass CLI (scripts/admin_login_code.py).

A correct password creates one pending sign-in: a random nonce (kept in the admin's
session cookie) bound to a 6-digit code (only its salted hash is stored). The code is
WhatsApped to ADMIN_ALERT_WHATSAPP; it is valid for CODE_TTL_MINUTES and MAX_ATTEMPTS
tries, and works only in the browser session that entered the password.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

CODE_TTL_MINUTES = 5
MAX_ATTEMPTS = 5


def _now():
    return datetime.now(timezone.utc)


def _hash(code, salt):
    return hashlib.sha256(f"{salt}:{code}".encode()).hexdigest()


def _new_code():
    return f"{secrets.randbelow(10**6):06d}"


def issue(conn, user_id, now=None):
    """Starts a pending sign-in for user_id (replacing any older one); returns (nonce, code)."""
    now = now or _now()
    nonce, code, salt = secrets.token_urlsafe(24), _new_code(), secrets.token_hex(16)
    conn.execute("DELETE FROM admin_login_codes WHERE user_id = ? OR expires_at < ?", (user_id, now.isoformat()))
    conn.execute(
        "INSERT INTO admin_login_codes (nonce, user_id, code_salt, code_hash, attempts, expires_at, created_at) "
        "VALUES (?, ?, ?, ?, 0, ?, ?)",
        (nonce, user_id, salt, _hash(code, salt),
         (now + timedelta(minutes=CODE_TTL_MINUTES)).isoformat(), now.isoformat()),
    )
    conn.commit()
    return nonce, code


def check(conn, nonce, code, now=None):
    """("ok", user_id) | ("wrong", tries_left) | ("expired", None). A used, expired or
    exhausted code is deleted, so it can never work twice."""
    now = now or _now()
    row = conn.execute("SELECT * FROM admin_login_codes WHERE nonce = ?", (nonce or "",)).fetchone()
    if row is None:
        return "expired", None
    if datetime.fromisoformat(row["expires_at"]) <= now or row["attempts"] >= MAX_ATTEMPTS:
        conn.execute("DELETE FROM admin_login_codes WHERE nonce = ?", (nonce,))
        conn.commit()
        return "expired", None
    if hmac.compare_digest(_hash((code or "").strip(), row["code_salt"]), row["code_hash"]):
        conn.execute("DELETE FROM admin_login_codes WHERE nonce = ?", (nonce,))
        conn.commit()
        return "ok", row["user_id"]
    attempts = row["attempts"] + 1
    if attempts >= MAX_ATTEMPTS:
        conn.execute("DELETE FROM admin_login_codes WHERE nonce = ?", (nonce,))
        conn.commit()
        return "expired", None
    conn.execute("UPDATE admin_login_codes SET attempts = ? WHERE nonce = ?", (attempts, nonce))
    conn.commit()
    return "wrong", MAX_ATTEMPTS - attempts


def reissue_for_username(conn, username, now=None):
    """Break-glass: a fresh code for username's pending sign-in (the browser keeps its
    nonce), or None if there is no unexpired one. Needs shell access to the server."""
    now = now or _now()
    row = conn.execute(
        "SELECT c.nonce FROM admin_login_codes c JOIN app_users u ON u.id = c.user_id "
        "WHERE u.username = ? AND c.expires_at > ? ORDER BY c.created_at DESC LIMIT 1",
        (username, now.isoformat()),
    ).fetchone()
    if row is None:
        return None
    code, salt = _new_code(), secrets.token_hex(16)
    conn.execute(
        "UPDATE admin_login_codes SET code_salt = ?, code_hash = ?, attempts = 0 WHERE nonce = ?",
        (salt, _hash(code, salt), row["nonce"]),
    )
    conn.commit()
    return code
