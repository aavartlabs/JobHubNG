"""Create an admin console account (app_users row), or reset its password.

    .venv/bin/python scripts/set_admin_password.py <username>

Prompts for the password without echoing it, so it never lands in shell history. Also
clears that username's admin-login lockout, so this doubles as the way to unlock it.
"""
import getpass
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from werkzeug.security import generate_password_hash

from jobhub_poc import db

_MIN_LENGTH = 12


def main() -> None:
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        sys.exit("usage: set_admin_password.py <username>")
    username = sys.argv[1].strip()

    password = getpass.getpass(f"New password for {username}: ")
    if len(password) < _MIN_LENGTH:
        sys.exit(f"Password must be at least {_MIN_LENGTH} characters.")
    if getpass.getpass("Again: ") != password:
        sys.exit("Passwords didn't match.")

    conn = db.get_connection()
    db.init_db(conn)
    conn.execute(
        """
        INSERT INTO app_users (username, password_hash, created_at) VALUES (?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash
        """,
        (username, generate_password_hash(password), datetime.now(timezone.utc).isoformat()),
    )
    conn.execute("DELETE FROM admin_login_attempts WHERE key = ?", (f"user:{username.lower()}",))
    conn.commit()
    print(f"Admin password set for {username}.")


if __name__ == "__main__":
    main()
