"""Check the admin's Telegram channel (admin_notify.py) end to end.

1. Open the JobsHub bot in Telegram and press Start: its reply shows your chat id.
2. Put it in .env as ADMIN_TELEGRAM_CHAT_ID.
3. Send a test admin message the way ops alerts and sign-in codes go:

    .venv/bin/python -m jobhub_poc.ops.telegram_setup test
"""
import sys

from jobhub_poc.admin_notify import notify_admin
from jobhub_poc.alerts.senders import LiveSender


def main():
    if sys.argv[1:] != ["test"]:
        sys.exit("usage: python -m jobhub_poc.ops.telegram_setup test")
    channel = notify_admin("JobsHub test: admin messages reach you here.", LiveSender())
    print(f"sent by {channel}")


if __name__ == "__main__":
    main()
