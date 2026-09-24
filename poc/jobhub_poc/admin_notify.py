"""Send one admin-only message: an ops alert or an admin sign-in code.

Telegram (through poc/telegram-gateway) first when ADMIN_TELEGRAM_CHAT_ID is set, then
the ADMIN_ALERT_WHATSAPP number through the WhatsApp gateway. Stops at the first channel that
takes the message; raises only if none did (or none is set), with every channel's reason.
Site users never get these.
"""
from jobhub_poc import config
from jobhub_poc.phone import normalize_e164


def _channels():
    if config.ADMIN_TELEGRAM_CHAT_ID.strip():
        yield "Telegram", "telegram", config.ADMIN_TELEGRAM_CHAT_ID.strip()
    number = normalize_e164(config.ADMIN_ALERT_WHATSAPP)
    if number:
        yield "WhatsApp", "whatsapp", number


def notify_admin(text, sender):
    """Returns the name of the channel that took the message."""
    failures = []
    for name, method, address in _channels():
        try:
            getattr(sender, method)(address, text)
            return name
        except Exception as exc:  # noqa: BLE001 -- try the next channel, report all at the end
            failures.append(f"{name}: {exc}")
    if not failures:
        raise RuntimeError(
            "no admin channel: set ADMIN_TELEGRAM_CHAT_ID, or ADMIN_ALERT_WHATSAPP to a "
            "+<country code><number>"
        )
    raise RuntimeError("admin message not sent -- " + "; ".join(failures))
