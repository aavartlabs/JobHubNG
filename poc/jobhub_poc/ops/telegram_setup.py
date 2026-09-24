"""Set up the admin's Telegram channel (admin_notify.py).

1. Create a bot with @BotFather; put its token in .env as TELEGRAM_BOT_TOKEN.
2. Open the bot in Telegram and press Start (a bot can't message anyone first).
3. List the chats that have messaged the bot, and put yours in .env as ADMIN_TELEGRAM_CHAT_ID:

    .venv/bin/python -m jobhub_poc.ops.telegram_setup chats

4. Send a test admin message the way ops alerts and sign-in codes go:

    .venv/bin/python -m jobhub_poc.ops.telegram_setup test
"""
import sys

import requests

from jobhub_poc import config
from jobhub_poc.admin_notify import notify_admin
from jobhub_poc.alerts.senders import TELEGRAM_API, LiveSender


def chats_from_updates(updates):
    """(chat id, who) for each distinct private chat in a getUpdates result, oldest first."""
    seen = {}
    for update in updates:
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat") or {}
        if chat.get("type") != "private" or chat.get("id") is None:
            continue
        name = " ".join(filter(None, [chat.get("first_name"), chat.get("last_name")]))
        if chat.get("username"):
            name = f"{name} (@{chat['username']})".strip()
        seen[str(chat["id"])] = name or "?"
    return list(seen.items())


def _get_updates():
    if not config.TELEGRAM_BOT_TOKEN:
        sys.exit("TELEGRAM_BOT_TOKEN is not set in .env")
    try:
        resp = requests.get(f"{TELEGRAM_API}/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates", timeout=20)
    except requests.RequestException as exc:
        sys.exit(f"Telegram unreachable ({type(exc).__name__})")  # not the URL: it holds the token
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    if not body.get("ok"):
        sys.exit(f"Telegram returned HTTP {resp.status_code}: {body.get('description', '')}")
    return body["result"]


def main():
    command = sys.argv[1] if len(sys.argv) == 2 else ""
    if command == "chats":
        chats = chats_from_updates(_get_updates())
        if not chats:
            sys.exit("No one has messaged the bot yet (or it was over a day ago): press Start, then rerun.")
        for chat_id, who in chats:
            print(f"{chat_id}\t{who}")
    elif command == "test":
        channel = notify_admin("JobsHub test: admin messages reach you here.", LiveSender())
        print(f"sent by {channel}")
    else:
        sys.exit("usage: python -m jobhub_poc.ops.telegram_setup chats|test")


if __name__ == "__main__":
    main()
