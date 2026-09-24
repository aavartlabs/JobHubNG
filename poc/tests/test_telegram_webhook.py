import requests

from jobhub_poc import config
from jobhub_poc.webapp.app import create_app

GATEWAY = "http://telegram.test"


def _client(conn, monkeypatch, url=GATEWAY):
    monkeypatch.setattr(config, "TELEGRAM_GATEWAY_URL", url)
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    return app.test_client()


def test_passes_body_and_secret_through_and_relays_the_answer(conn, monkeypatch, requests_mock):
    upstream = requests_mock.post(f"{GATEWAY}/webhook", status_code=401, json={"error": "unauthorized"})
    resp = _client(conn, monkeypatch).post(
        "/telegram/webhook", data=b'{"update_id": 1}',
        headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret", "Content-Type": "application/json"},
    )
    assert resp.status_code == 401
    assert upstream.last_request.body == b'{"update_id": 1}'
    assert upstream.last_request.headers["X-Telegram-Bot-Api-Secret-Token"] == "s3cret"


def test_gateway_down_is_a_502_so_telegram_retries(conn, monkeypatch, requests_mock):
    requests_mock.post(f"{GATEWAY}/webhook", exc=requests.ConnectionError)
    assert _client(conn, monkeypatch).post("/telegram/webhook", json={}).status_code == 502


def test_unconfigured_or_oversized_is_refused(conn, monkeypatch, requests_mock):
    assert _client(conn, monkeypatch, url="").post("/telegram/webhook", json={}).status_code == 503
    big = b"x" * (64 * 1024 + 1)
    assert _client(conn, monkeypatch).post("/telegram/webhook", data=big).status_code == 413
    assert requests_mock.call_count == 0


def test_only_post(conn, monkeypatch):
    assert _client(conn, monkeypatch).get("/telegram/webhook").status_code == 405
