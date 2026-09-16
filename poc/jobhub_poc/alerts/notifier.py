"""Pluggable alert-send backends.

ConsoleNotifier logs to stdout and the alerts_sent table -- useful for
demoing without a live WhatsApp session. WhatsAppNotifier calls the small
Node/baileys gateway in whatsapp-sender/ (see that directory's README) over
HTTP; it requires the gateway to have already been QR-paired with a real
WhatsApp account -- see whatsapp-sender/README.md for the one-time pairing
step, which cannot be scripted.
"""
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import requests

from jobhub_poc import config
from jobhub_poc.alerts.matcher import Match


class Notifier(ABC):
    backend_name: str

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    @abstractmethod
    def _deliver(self, match: Match) -> str:
        """Deliver the message and return it (or raise on failure)."""

    def send(self, match: Match) -> None:
        already_sent = self.conn.execute(
            "SELECT 1 FROM alerts_sent WHERE subscription_id = ? AND job_id = ?",
            (match.subscription_id, match.job_id),
        ).fetchone()
        if already_sent:
            return

        try:
            message = self._deliver(match)
            status = "SENT"
        except Exception:
            message = f"New job matching your alert: {match.job_title} ({match.job_location})"
            status = "FAILED"

        try:
            self.conn.execute(
                """
                INSERT INTO alerts_sent (subscription_id, job_id, notifier_backend, message, sent_at, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (match.subscription_id, match.job_id, self.backend_name, message,
                 datetime.now(timezone.utc).isoformat(), status),
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            pass  # lost a race with another send for the same (subscription, job); fine


class ConsoleNotifier(Notifier):
    backend_name = "console"

    def _deliver(self, match: Match) -> str:
        message = f"New job matching your alert: {match.job_title} ({match.job_location})"
        print(f"[ConsoleNotifier] -> {match.phone_number}: {message}")
        return message


class WhatsAppNotifier(Notifier):
    backend_name = "whatsapp"

    def __init__(self, conn: sqlite3.Connection, gateway_url: str | None = None,
                 api_key: str | None = None, timeout_seconds: int = 15):
        super().__init__(conn)
        self.gateway_url = gateway_url if gateway_url is not None else config.WHATSAPP_GATEWAY_URL
        self.api_key = api_key if api_key is not None else config.WHATSAPP_GATEWAY_API_KEY
        self.timeout_seconds = timeout_seconds

    def _deliver(self, match: Match) -> str:
        if not self.gateway_url:
            raise RuntimeError("WHATSAPP_GATEWAY_URL is not configured")

        message = f"New job matching your alert: {match.job_title} ({match.job_location})"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        resp = requests.post(
            f"{self.gateway_url.rstrip('/')}/send",
            json={"phone": match.phone_number, "message": message},
            headers=headers,
            timeout=self.timeout_seconds,
        )
        if resp.status_code >= 300:
            raise RuntimeError(f"WhatsApp gateway returned HTTP {resp.status_code}: {resp.text[:300]}")
        return message


def get_notifier(backend: str, conn: sqlite3.Connection) -> Notifier:
    if backend == "console":
        return ConsoleNotifier(conn)
    if backend == "whatsapp":
        return WhatsAppNotifier(conn)
    raise ValueError(f"unknown notifier backend: {backend!r}")
