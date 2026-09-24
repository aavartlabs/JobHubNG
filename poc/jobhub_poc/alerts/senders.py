"""How a message actually leaves: WhatsApp via the whatsapp-sender gateway, email via
Resend, Telegram via the Bot API (admin messages only, for now -- admin_notify.py), or --
NOTIFIER_BACKEND=console -- printed instead of sent (dev and dry runs).

Every send raises on failure, so the caller records it as FAILED rather than SENT.
"""
import requests

from jobhub_poc import config

RESEND_URL = "https://api.resend.com/emails"
TELEGRAM_API = "https://api.telegram.org"
# Above whatsapp-sender's own ACK_TIMEOUT_MS (45s on pi09) so its timeout reaches us as a
# clean HTTP error rather than us giving up on the connection first.
_WHATSAPP_TIMEOUT_SECONDS = 55
_EMAIL_TIMEOUT_SECONDS = 20
_TELEGRAM_TIMEOUT_SECONDS = 20


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
        if not config.TELEGRAM_BOT_TOKEN:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
        # The token is part of the URL, so no requests error (which quotes the URL) is let
        # through: it would land in backup.log and the app log.
        try:
            resp = requests.post(
                f"{TELEGRAM_API}/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
                timeout=_TELEGRAM_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Telegram unreachable ({type(exc).__name__})") from None
        if resp.status_code >= 300:
            try:
                reason = resp.json().get("description", "")
            except ValueError:
                reason = ""
            raise RuntimeError(f"Telegram returned HTTP {resp.status_code}: {reason[:300]}")


def get_senders(backend):
    """"console", or "live" ("whatsapp" is accepted too: it was the pre-v2 setting)."""
    if backend == "console":
        return ConsoleSender()
    if backend in ("live", "whatsapp"):
        return LiveSender()
    raise ValueError(f"unknown notifier backend: {backend!r}")
