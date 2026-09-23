"""Send each matched alert's digest on each channel it asked for, and record the outcome
per job in alerts_sent (SENT / FAILED / SKIPPED). Jobs already recorded for that alert and
channel are left out, so re-running a run never re-sends."""
from datetime import datetime, timezone

from jobhub_poc.alerts.digest import build_email, build_whatsapp


def _pending(conn, match, channel):
    done = {r[0] for r in conn.execute(
        "SELECT job_id FROM alerts_sent WHERE subscription_id = ? AND channel = ?", (match.subscription_id, channel))}
    return [job for job in match.jobs if job["id"] not in done]


def _record(conn, match, jobs, channel, backend, message, status):
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        """INSERT OR IGNORE INTO alerts_sent
               (subscription_id, job_id, channel, notifier_backend, message, sent_at, status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [(match.subscription_id, job["id"], channel, backend, message, now, status) for job in jobs],
    )
    conn.commit()


def deliver(conn, matches, contacts, sender, backend, origin):
    """contacts: {owner id: Contact}. Returns counts of digests sent/failed, channels
    skipped as unverified, and alerts deactivated because their owner no longer exists."""
    stats = {"digests_sent": 0, "digests_failed": 0, "skipped": 0, "deactivated": 0}
    for match in matches:
        contact = contacts.get(match.owner_auth_user_id)
        if contact is None:
            conn.execute("UPDATE alert_subscriptions SET is_active = 0 WHERE id = ?", (match.subscription_id,))
            conn.commit()
            stats["deactivated"] += 1
            continue

        channels = [c for c, wanted in (("email", match.notify_email), ("whatsapp", match.notify_whatsapp)) if wanted]
        for channel in channels:
            jobs = _pending(conn, match, channel)
            if not jobs:
                continue
            address, verified = ((contact.email, contact.email_verified) if channel == "email"
                                 else (contact.phone, contact.phone_verified))
            if not (address and verified):
                _record(conn, match, jobs, channel, backend, f"{channel} not verified", "SKIPPED")
                stats["skipped"] += 1
                continue
            try:
                if channel == "email":
                    subject, text, html = build_email(match.rule, jobs, origin)
                    sender.email(address, subject, text, html)
                    message = subject
                else:
                    message = build_whatsapp(match.rule, jobs, origin)
                    sender.whatsapp(address, message)
                status = "SENT"
                stats["digests_sent"] += 1
            except Exception as exc:  # noqa: BLE001 -- any failure is recorded, never fatal to the run
                message, status = f"send failed: {exc}"[:500], "FAILED"
                stats["digests_failed"] += 1
            _record(conn, match, jobs, channel, backend, message, status)
    return stats
