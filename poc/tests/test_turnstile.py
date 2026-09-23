import requests
import pytest
from flask import Flask

from jobhub_poc import config
from jobhub_poc.webapp import turnstile

SITEVERIFY = turnstile.SITEVERIFY_URL


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(config, "CF_TURNSTILE_SECRET", "real-secret")
    monkeypatch.setattr(config, "TURNSTILE_HOSTNAMES", {"jobhubs.example.com"})
    monkeypatch.setattr(config, "TURNSTILE_ALLOW_TEST_KEYS", False)
    return Flask(__name__)


def _ok(**overrides):
    body = {"success": True, "action": "signup", "hostname": "jobhubs.example.com", "error-codes": []}
    body.update(overrides)
    return body


def _verify(app, token="tok", action="signup", headers=None):
    with app.test_request_context("/", headers=headers or {"CF-Connecting-IP": "203.0.113.9"}):
        return turnstile.verify(token, action)


def test_accepts_matching_success_action_and_hostname(app, requests_mock):
    requests_mock.post(SITEVERIFY, json=_ok())
    assert _verify(app) is True
    sent = requests_mock.last_request.text
    assert "secret=real-secret" in sent
    assert "response=tok" in sent
    assert "remoteip=203.0.113.9" in sent


@pytest.mark.parametrize("overrides", [
    {"success": False, "error-codes": ["invalid-input-response"]},
    {"action": "login"},
    {"hostname": "evil.example.com"},
    {"hostname": "localhost"},
])
def test_rejects_any_mismatch(app, requests_mock, overrides):
    requests_mock.post(SITEVERIFY, json=_ok(**overrides))
    assert _verify(app) is False


@pytest.mark.parametrize("token", ["", None, "x" * 2049])
def test_rejects_missing_or_oversized_token_without_calling_cloudflare(app, requests_mock, token):
    requests_mock.post(SITEVERIFY, json=_ok())
    assert _verify(app, token=token) is False
    assert requests_mock.call_count == 0


def test_fails_closed_when_secret_unset(app, requests_mock, monkeypatch):
    monkeypatch.setattr(config, "CF_TURNSTILE_SECRET", "")
    requests_mock.post(SITEVERIFY, json=_ok())
    assert _verify(app) is False
    assert requests_mock.call_count == 0


def test_fails_closed_on_network_error_or_non_json(app, requests_mock):
    requests_mock.post(SITEVERIFY, exc=requests.exceptions.ConnectTimeout)
    assert _verify(app) is False
    requests_mock.post(SITEVERIFY, text="<html>", status_code=502)
    assert _verify(app) is False


def test_testing_key_result_rejected_unless_explicitly_allowed(app, requests_mock, monkeypatch):
    # Cloudflare's test secret returns hostname example.com and no action at all.
    testing = {"success": True, "hostname": "example.com", "metadata": {"result_with_testing_key": True}}
    requests_mock.post(SITEVERIFY, json=testing)
    assert _verify(app) is False
    monkeypatch.setattr(config, "TURNSTILE_ALLOW_TEST_KEYS", True)
    assert _verify(app) is True


def test_default_hostnames_come_from_web_origin():
    assert config.hostnames_from_origin("https://jobhubs.aavartlabs.com") == {"jobhubs.aavartlabs.com"}
    assert config.hostnames_from_origin("http://localhost:8100") == {"localhost"}
