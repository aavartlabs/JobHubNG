import pytest

from jobhub_poc import config
from jobhub_poc.alerts.senders import RESEND_URL, ConsoleSender, LiveSender, get_senders

GATEWAY = "http://gateway.test"


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(config, "WHATSAPP_GATEWAY_URL", GATEWAY)
    monkeypatch.setattr(config, "WHATSAPP_GATEWAY_API_KEY", "wa-key")
    monkeypatch.setattr(config, "RESEND_API_KEY", "re_key")
    monkeypatch.setattr(config, "RESEND_FROM_EMAIL", "JobsHub <noreply@alerts.example>")
    monkeypatch.setattr(config, "WEB_ORIGIN", "https://jobhubs.example")


def test_backend_names():
    assert isinstance(get_senders("console"), ConsoleSender)
    assert isinstance(get_senders("live"), LiveSender)
    assert isinstance(get_senders("whatsapp"), LiveSender)  # prod's existing value
    with pytest.raises(ValueError):
        get_senders("carrier-pigeon")


def test_whatsapp_goes_through_the_gateway(requests_mock):
    requests_mock.post(f"{GATEWAY}/send", json={"status": "sent"})
    LiveSender().whatsapp("+15550000001", "hello")
    req = requests_mock.last_request
    assert req.json() == {"phone": "+15550000001", "message": "hello"}
    assert req.headers["x-api-key"] == "wa-key"


def test_whatsapp_gateway_errors_raise(requests_mock):
    requests_mock.post(f"{GATEWAY}/send", status_code=422, json={"error": "not_on_whatsapp"})
    with pytest.raises(RuntimeError, match="not_on_whatsapp"):
        LiveSender().whatsapp("+15550000001", "hello")


def test_email_goes_through_resend_with_unsubscribe_header(requests_mock):
    requests_mock.post(RESEND_URL, json={"id": "e1"})
    LiveSender().email("a@x.com", "Subj", "text body", "<p>html</p>")
    req = requests_mock.last_request
    assert req.headers["Authorization"] == "Bearer re_key"
    body = req.json()
    assert body["from"] == "JobsHub <noreply@alerts.example>"
    assert body["to"] == ["a@x.com"]
    assert (body["subject"], body["text"], body["html"]) == ("Subj", "text body", "<p>html</p>")
    assert body["headers"]["List-Unsubscribe"] == "<https://jobhubs.example/alerts>"


def test_email_errors_and_missing_config_raise(requests_mock, monkeypatch):
    requests_mock.post(RESEND_URL, status_code=403, json={"message": "domain not verified"})
    with pytest.raises(RuntimeError, match="domain not verified"):
        LiveSender().email("a@x.com", "s", "t", "h")
    monkeypatch.setattr(config, "RESEND_FROM_EMAIL", "")
    with pytest.raises(RuntimeError, match="RESEND_FROM_EMAIL"):
        LiveSender().email("a@x.com", "s", "t", "h")


def test_console_sender_prints_and_sends_nothing(capsys, requests_mock):
    ConsoleSender().whatsapp("+15550000001", "wa text")
    ConsoleSender().email("a@x.com", "subj", "mail text", "<p/>")
    out = capsys.readouterr().out
    assert "+15550000001" in out and "wa text" in out and "a@x.com" in out and "subj" in out
    assert requests_mock.call_count == 0


TELEGRAM_GATEWAY = "http://telegram.test"


@pytest.fixture
def tg(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_GATEWAY_URL", TELEGRAM_GATEWAY)
    monkeypatch.setattr(config, "TELEGRAM_GATEWAY_API_KEY", "tg-key")


def test_telegram_goes_through_the_gateway(requests_mock, tg):
    requests_mock.post(f"{TELEGRAM_GATEWAY}/send", json={"status": "sent", "message_id": 1})
    LiveSender().telegram(4242, "hello")
    req = requests_mock.last_request
    assert req.json() == {"chat_id": "4242", "text": "hello"}
    assert req.headers["x-api-key"] == "tg-key"


def test_telegram_blocked_and_other_errors_raise(requests_mock, tg):
    requests_mock.post(f"{TELEGRAM_GATEWAY}/send", status_code=410, json={"error": "blocked"})
    with pytest.raises(RuntimeError, match="blocked the Telegram bot"):
        LiveSender().telegram("4242", "hello")
    requests_mock.post(f"{TELEGRAM_GATEWAY}/send", status_code=502, json={"error": "send_failed"})
    with pytest.raises(RuntimeError, match="HTTP 502: send_failed"):
        LiveSender().telegram("4242", "hello")


def test_telegram_needs_the_gateway(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_GATEWAY_URL", "")
    with pytest.raises(RuntimeError, match="TELEGRAM_GATEWAY_URL"):
        LiveSender().telegram("4242", "hello")


def test_console_sender_prints_telegram(capsys):
    ConsoleSender().telegram("4242", "tg text")
    out = capsys.readouterr().out
    assert "4242" in out and "tg text" in out
