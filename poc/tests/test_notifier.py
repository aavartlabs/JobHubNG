import pytest

from jobhub_poc.alerts.matcher import Match
from jobhub_poc.alerts.notifier import ConsoleNotifier, WhatsAppNotifier, get_notifier


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


def test_alert_message_is_branded_with_jobhubng_header(conn):
    match = _seed_match(conn)
    notifier = ConsoleNotifier(conn)
    notifier.send(match)
    row = conn.execute("SELECT message FROM alerts_sent").fetchone()
    assert row["message"].startswith("*JobHubNG Alert*")
    assert "Engineer" in row["message"]


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


def test_get_notifier_whatsapp_returns_whatsapp_notifier(conn):
    notifier = get_notifier("whatsapp", conn=conn)
    assert isinstance(notifier, WhatsAppNotifier)


def test_whatsapp_notifier_sends_via_gateway_and_logs_sent(conn, requests_mock):
    requests_mock.post("http://gateway.test/send", json={"status": "sent"})
    match = _seed_match(conn, phone="+15551234567")
    notifier = WhatsAppNotifier(conn, gateway_url="http://gateway.test", api_key="secret-key")
    notifier.send(match)

    sent = requests_mock.request_history[0]
    assert sent.headers["x-api-key"] == "secret-key"
    assert sent.json() == {
        "phone": "+15551234567",
        "message": "*JobHubNG Alert*\nNew job matching your alert: Engineer (Remote)",
    }
    row = conn.execute("SELECT * FROM alerts_sent").fetchone()
    assert row["notifier_backend"] == "whatsapp"
    assert row["status"] == "SENT"


def test_whatsapp_notifier_gateway_error_marks_failed_not_a_crash(conn, requests_mock):
    requests_mock.post("http://gateway.test/send", status_code=503, text="not paired yet")
    match = _seed_match(conn)
    notifier = WhatsAppNotifier(conn, gateway_url="http://gateway.test")
    notifier.send(match)  # must not raise

    row = conn.execute("SELECT * FROM alerts_sent").fetchone()
    assert row["notifier_backend"] == "whatsapp"
    assert row["status"] == "FAILED"


def test_whatsapp_notifier_missing_gateway_url_marks_failed_not_a_crash(conn):
    match = _seed_match(conn)
    notifier = WhatsAppNotifier(conn, gateway_url="")
    notifier.send(match)  # must not raise

    row = conn.execute("SELECT * FROM alerts_sent").fetchone()
    assert row["status"] == "FAILED"
