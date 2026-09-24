from datetime import datetime

import pytest

from jobhub_poc import config
from jobhub_poc.ops.alert_admin import build_message, send_alert, tail


class FakeSender:
    def __init__(self):
        self.sent = []

    def telegram(self, chat_id, text):
        self.sent.append((chat_id, text))

    def whatsapp(self, phone, text):
        self.sent.append((phone, text))


@pytest.fixture(autouse=True)
def whatsapp_only(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TELEGRAM_CHAT_ID", "")
    monkeypatch.setattr(config, "ADMIN_ALERT_WHATSAPP", "+91 99020 00000")


def test_sends_to_admin_number_with_unit_and_log_tail(tmp_path):
    log = tmp_path / "backup.log"
    log.write_text("".join(f"line {i}\n" for i in range(20)) + "\nFAIL pi05/warehouse.db no backup found\n")
    sender = FakeSender()

    send_alert("jobshub-backup.service", sender, log_path=log,
               host="pi09", now=datetime(2026, 9, 24, 2, 31))

    [(phone, text)] = sender.sent
    assert phone == "+919902000000"
    assert text.startswith("JobsHub ops alert: jobshub-backup.service FAILED on pi09 at 2026-09-24 02:31.")
    assert "FAIL pi05/warehouse.db no backup found" in text
    assert "line 0\n" not in text  # only the tail
    assert "systemctl --user status jobshub-backup.service" in text


@pytest.mark.parametrize("phone", ["", "9902000000", "+0123456789"])
def test_refuses_without_a_valid_admin_number(tmp_path, monkeypatch, phone):
    monkeypatch.setattr(config, "ADMIN_ALERT_WHATSAPP", phone)
    sender = FakeSender()
    with pytest.raises(RuntimeError, match="ADMIN_ALERT_WHATSAPP"):
        send_alert("x.service", sender, log_path=tmp_path / "none.log")
    assert sender.sent == []


def test_missing_log_still_alerts(tmp_path):
    assert tail(tmp_path / "missing.log") == []
    text = build_message("x.service", "pi09", datetime(2026, 9, 24), [])
    assert "Last log lines" not in text and "x.service FAILED" in text


def test_goes_to_telegram_when_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TELEGRAM_CHAT_ID", "4242")
    sender = FakeSender()
    send_alert("x.service", sender, log_path=tmp_path / "none.log", host="pi09")
    [(chat_id, text)] = sender.sent
    assert chat_id == "4242" and "x.service FAILED on pi09" in text
