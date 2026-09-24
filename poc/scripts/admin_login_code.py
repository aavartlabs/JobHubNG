"""Break-glass for the admin console's sign-in code step: prints a fresh code for
<username>'s pending sign-in, for when the Telegram/WhatsApp message didn't arrive (both
channels down or unset). Enter the password on /admin/login first, then run this within 5 minutes:

    .venv/bin/python scripts/admin_login_code.py <username>

Only someone with a shell on the server can run it, which already beats the second factor.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobhub_poc import admin_codes, db


def main() -> None:
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        sys.exit("usage: admin_login_code.py <username>")
    username = sys.argv[1].strip()
    conn = db.get_connection()
    db.init_db(conn)
    code = admin_codes.reissue_for_username(conn, username)
    if code is None:
        sys.exit(f"No pending sign-in for {username}: enter the password on /admin/login first.")
    print(f"Sign-in code for {username}: {code} (valid until the pending sign-in expires)")


if __name__ == "__main__":
    main()
