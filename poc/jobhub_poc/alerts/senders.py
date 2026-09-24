"""How a message actually leaves: Telegram via poc/telegram-gateway (alert digests and
admin messages), email via Resend, WhatsApp via the whatsapp-sender gateway (admin
fallback only, admin_notify.py), or -- NOTIFIER_BACKEND=console -- printed instead of
sent (dev and dry runs).

Every send raises on failure, so the caller records it as FAILED rather than SENT.
"""
import requests

from jobhub_poc import config

RESEND_URL = "https://api.resend.com/emails"
# Above whatsapp-sender's own ACK_TIMEOUT_MS (45s on pi09) so its timeout reaches us as a
# clean HTTP error rather than us giving up on the connection first.
_WHATSAPP_TIMEOUT_SECONDS = 55
_EMAIL_TIMEOUT_SECONDS = 20
# Above the gateway's own Bot API timeout (20s) plus one 429 wait (10s).
_TELEGRAM_TIMEOUT_SECONDS = 35


class ConsoleSender:
    def whatsapp(self, phone, text):
        print(f"[console whatsapp] -> {phone}\n{text}\n")

    def email(self, to, subject, text, html):
        print(f"[console email] -> {to}: {subject}\n{text}\n")

    def telegram(self, chat_id, text):
        print(f"[console telegram] -> {chat_id}\n{text}\n")


class LiveSender:
    def whatsapp(self, phone, text):
        if not config.WHATSAPP_GATEWAY_URL:
            raise RuntimeError("WHATSAPP_GATEWAY_URL is not configured")
        headers = {"Content-Type": "application/json"}
        if config.WHATSAPP_GATEWAY_API_KEY:
            headers["x-api-key"] = config.WHATSAPP_GATEWAY_API_KEY
        resp = requests.post(
            f"{config.WHATSAPP_GATEWAY_URL.rstrip('/')}/send",
            json={"phone": phone, "message": text},
            headers=headers,
            timeout=_WHATSAPP_TIMEOUT_SECONDS,
        )
        if resp.status_code >= 300:
            raise RuntimeError(f"WhatsApp gateway returned HTTP {resp.status_code}: {resp.text[:300]}")

    def email(self, to, subject, text, html):
        if not config.RESEND_API_KEY or not config.RESEND_FROM_EMAIL:
            raise RuntimeError("RESEND_API_KEY / RESEND_FROM_EMAIL are not configured")
        resp = requests.post(
            RESEND_URL,
            headers={"Authorization": f"Bearer {config.RESEND_API_KEY}"},
            json={
                "from": config.RESEND_FROM_EMAIL,
                "to": [to],
                "subject": subject,
                "text": text,
                "html": html,
                # Lets mail clients offer "unsubscribe", which also helps deliverability.
                "headers": {"List-Unsubscribe": f"<{config.WEB_ORIGIN}/alerts>"},
            },
            timeout=_EMAIL_TIMEOUT_SECONDS,
        )
        if resp.status_code >= 300:
            raise RuntimeError(f"Resend returned HTTP {resp.status_code}: {resp.text[:300]}")

    def telegram(self, chat_id, text):
        if not config.TELEGRAM_GATEWAY_URL:
            raise RuntimeError("TELEGRAM_GATEWAY_URL is not configured")
        resp = requests.post(
            f"{config.TELEGRAM_GATEWAY_URL.rstrip('/')}/send",
            json={"chat_id": str(chat_id), "text": text},
            headers={"x-api-key": config.TELEGRAM_GATEWAY_API_KEY},
            timeout=_TELEGRAM_TIMEOUT_SECONDS,
        )
        if resp.status_code >= 300:
            try:
                error = resp.json().get("error", "")
            except ValueError:
                error = resp.text[:300]
            if error == "blocked":
                raise RuntimeError("the user has blocked the Telegram bot")
            raise RuntimeError(f"Telegram gateway returned HTTP {resp.status_code}: {error}")


def get_senders(backend):
    """"console", or "live" ("whatsapp" is accepted too: it was the pre-v2 setting)."""
    if backend == "console":
        return ConsoleSender()
    if backend in ("live", "whatsapp"):
        return LiveSender()
    raise ValueError(f"unknown notifier backend: {backend!r}")
