"""Pluggable alert-send backends.

Only ConsoleNotifier ships for the Saturday POC -- it logs to stdout and to
the alerts_sent table, which is what the demo shows as evidence an alert
"fired". A real WhatsApp backend (NOTIFIER_BACKEND=whatsapp) is a fast-follow:
implement WhatsAppNotifier.send() the same shape, register it in
get_notifier(), no changes needed anywhere else.
"""
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timezone

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


def get_notifier(backend: str, conn: sqlite3.Connection) -> Notifier:
    if backend == "console":
        return ConsoleNotifier(conn)
    raise ValueError(f"unknown notifier backend: {backend!r}")
