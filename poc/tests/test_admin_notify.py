import pytest

from jobhub_poc import admin_notify, config


class FakeSender:
    def __init__(self, fail=()):
        self.sent, self.fail = [], set(fail)

    def telegram(self, chat_id, text):
        if "telegram" in self.fail:
            raise RuntimeError("telegram down")
        self.sent.append(("telegram", chat_id, text))

    def whatsapp(self, phone, text):
        if "whatsapp" in self.fail:
            raise RuntimeError("gateway down")
        self.sent.append(("whatsapp", phone, text))


@pytest.fixture
def both(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TELEGRAM_CHAT_ID", "4242")
    monkeypatch.setattr(config, "ADMIN_ALERT_WHATSAPP", "+91 90000 00001")


def test_telegram_first_and_only_once(both):
    sender = FakeSender()
    assert admin_notify.notify_admin("hi", sender) == "Telegram"
    assert sender.sent == [("telegram", "4242", "hi")]


def test_falls_back_to_whatsapp_when_telegram_fails(both):
    sender = FakeSender(fail={"telegram"})
    assert admin_notify.notify_admin("hi", sender) == "WhatsApp"
    assert sender.sent == [("whatsapp", "+919000000001", "hi")]


def test_whatsapp_only_when_telegram_is_not_configured(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TELEGRAM_CHAT_ID", "")
    monkeypatch.setattr(config, "ADMIN_ALERT_WHATSAPP", "+91 90000 00001")
    sender = FakeSender()
    assert admin_notify.notify_admin("hi", sender) == "WhatsApp"


def test_every_channel_failing_raises_with_each_reason(both):
    with pytest.raises(RuntimeError, match="telegram down.*gateway down"):
        admin_notify.notify_admin("hi", FakeSender(fail={"telegram", "whatsapp"}))


@pytest.mark.parametrize("phone", ["", "9902000000"])
def test_nothing_configured_raises_naming_both_settings(monkeypatch, phone):
    monkeypatch.setattr(config, "ADMIN_TELEGRAM_CHAT_ID", "")
    monkeypatch.setattr(config, "ADMIN_ALERT_WHATSAPP", phone)
    sender = FakeSender()
    with pytest.raises(RuntimeError, match="ADMIN_TELEGRAM_CHAT_ID.*ADMIN_ALERT_WHATSAPP"):
        admin_notify.notify_admin("hi", sender)
    assert sender.sent == []
