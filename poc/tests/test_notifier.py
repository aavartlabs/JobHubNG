import pytest

from jobhub_poc.alerts.matcher import Match
from jobhub_poc.alerts.notifier import ConsoleNotifier, get_notifier


def _seed_match(conn, phone="+1000", title="Engineer", location="Remote"):
    job_id = conn.execute(
        """
        INSERT INTO jobs (dedupe_key, source_site, title, location, first_seen_at, last_seen_at, raw_json)
        VALUES (?, 'acme', ?, ?, '2026-09-16T00:00:00+00:00', '2026-09-16T00:00:00+00:00', '{}')
        """,
        (title, title, location),
    ).lastrowid
    sub_id = conn.execute(
        """
        INSERT INTO alert_subscriptions (phone_number, title_keyword, is_active, created_at)
        VALUES (?, NULL, 1, '2026-09-16T00:00:00+00:00')
        """,
        (phone,),
    ).lastrowid
    conn.commit()
    return Match(subscription_id=sub_id, job_id=job_id, phone_number=phone,
                 job_title=title, job_location=location)


def test_console_notifier_prints_and_logs_sent(conn, capsys):
    match = _seed_match(conn)
    notifier = ConsoleNotifier(conn)
    notifier.send(match)
    captured = capsys.readouterr()
    assert "+1000" in captured.out
    assert "Engineer" in captured.out
    row = conn.execute("SELECT * FROM alerts_sent").fetchone()
    assert row["notifier_backend"] == "console"
    assert row["status"] == "SENT"


def test_double_send_same_subscription_and_job_is_idempotent_not_a_crash(conn):
    match = _seed_match(conn)
    notifier = ConsoleNotifier(conn)
    notifier.send(match)
    notifier.send(match)  # same subscription_id/job_id again
    rows = conn.execute("SELECT * FROM alerts_sent").fetchall()
    assert len(rows) == 1


def test_get_notifier_unknown_backend_raises(conn):
    with pytest.raises(ValueError):
        get_notifier("bogus", conn=conn)


def test_get_notifier_console_returns_console_notifier(conn):
    notifier = get_notifier("console", conn=conn)
    assert isinstance(notifier, ConsoleNotifier)
