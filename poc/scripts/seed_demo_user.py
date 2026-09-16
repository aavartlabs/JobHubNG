"""Create the single demo login from WEB_ADMIN_USERNAME/WEB_ADMIN_PASSWORD. Idempotent."""
import sys
from datetime import datetime, timezone
from pathlib import Path

from werkzeug.security import generate_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobhub_poc import config, db


def main() -> None:
    conn = db.get_connection()
    db.init_db(conn)
    existing = conn.execute(
        "SELECT id FROM app_users WHERE username = ?", (config.WEB_ADMIN_USERNAME,)
    ).fetchone()
    if existing:
        print(f"user {config.WEB_ADMIN_USERNAME!r} already exists (id={existing['id']}), skipping")
        return

    conn.execute(
        "INSERT INTO app_users (username, password_hash, created_at) VALUES (?, ?, ?)",
        (config.WEB_ADMIN_USERNAME, generate_password_hash(config.WEB_ADMIN_PASSWORD),
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    print(f"created user {config.WEB_ADMIN_USERNAME!r}")


if __name__ == "__main__":
    main()
