"""Encryption at rest for resumes and everything derived from them (Fernet: AES-128-CBC +
HMAC-SHA256). The key lives in .env (RESUME_ENCRYPTION_KEY), never in the database, so
jobhub.db and its nightly MinIO backups hold only ciphertext for this data."""
import json

from cryptography.fernet import Fernet, InvalidToken

from jobhub_poc import config


class CryptoUnavailable(RuntimeError):
    """No usable RESUME_ENCRYPTION_KEY: resume features are switched off."""


def enabled():
    try:
        _fernet()
        return True
    except CryptoUnavailable:
        return False


def _fernet():
    key = config.RESUME_ENCRYPTION_KEY
    if not key:
        raise CryptoUnavailable("RESUME_ENCRYPTION_KEY is not set")
    try:
        return Fernet(key)
    except (ValueError, TypeError) as exc:
        raise CryptoUnavailable("RESUME_ENCRYPTION_KEY is not a valid Fernet key") from exc


def encrypt(data: bytes) -> bytes:
    return _fernet().encrypt(data)


def decrypt(token: bytes) -> bytes:
    try:
        return _fernet().decrypt(token)
    except InvalidToken as exc:
        raise CryptoUnavailable("can't decrypt: wrong RESUME_ENCRYPTION_KEY or damaged data") from exc


def encrypt_json(value) -> bytes:
    return encrypt(json.dumps(value, ensure_ascii=False).encode())


def decrypt_json(token: bytes):
    return json.loads(decrypt(token))


def new_key() -> str:
    """For setup: `python -c "from jobhub_poc.crypto import new_key; print(new_key())"`."""
    return Fernet.generate_key().decode()
