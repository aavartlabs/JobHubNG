"""Where each alert owner's digests go: their account's email and mobile, and whether
each is verified. Read once per pipeline run from auth-service -- alerts no longer store
a phone number of their own, so an edited or re-verified contact takes effect at once.
"""
from dataclasses import dataclass

from jobhub_poc import auth_admin_client


@dataclass(frozen=True)
class Contact:
    email: str | None
    email_verified: bool
    phone: str | None
    phone_verified: bool


def load_contacts():
    """{auth user id: Contact}. Raises auth_admin_client.AuthServiceError if auth-service
    can't be reached -- a run must not guess who to message."""
    users = auth_admin_client.call("GET")["users"]
    return {
        u["id"]: Contact(
            email=u.get("email"),
            email_verified=bool(u.get("emailVerified")),
            phone=u.get("phoneNumber"),
            phone_verified=bool(u.get("phoneNumberVerified")),
        )
        for u in users
    }
