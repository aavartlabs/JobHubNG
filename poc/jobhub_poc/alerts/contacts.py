"""Where each alert owner's digests go: their account's email and linked Telegram chat,
and whether each is verified. Read once per pipeline run from auth-service -- alerts
store no address of their own, so an edited or re-linked contact takes effect at once.
"""
from dataclasses import dataclass

from jobhub_poc import auth_admin_client


@dataclass(frozen=True)
class Contact:
    email: str | None
    email_verified: bool
    telegram_chat_id: str | None
    telegram_verified: bool


def load_contacts():
    """{auth user id: Contact}. Raises auth_admin_client.AuthServiceError if auth-service
    can't be reached -- a run must not guess who to message."""
    users = auth_admin_client.call("GET")["users"]
    return {
        u["id"]: Contact(
            email=u.get("email"),
            email_verified=bool(u.get("emailVerified")),
            telegram_chat_id=u.get("telegramChatId"),
            telegram_verified=bool(u.get("telegramVerified")),
        )
        for u in users
    }
