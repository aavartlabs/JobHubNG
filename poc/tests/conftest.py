import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobhub_poc import db


@pytest.fixture
def conn():
    c = db.get_connection(":memory:")
    db.init_db(c)
    yield c
    c.close()


@pytest.fixture
def turnstile_calls(monkeypatch):
    """Replaces turnstile.verify (tested on its own in test_turnstile.py) with a fake
    that accepts only the token "good-token" and records every (token, action) it saw."""
    from jobhub_poc.webapp import turnstile

    calls = []

    def fake_verify(token, action):
        calls.append((token, action))
        return token == "good-token"

    monkeypatch.setattr(turnstile, "verify", fake_verify)
    return calls


@pytest.fixture(autouse=True)
def _no_openrouter_model_list(monkeypatch):
    """ai/openrouter.py fetches OpenRouter's public model list to see which parameters a model
    takes; tests never go to the network for it (as if unknown, unless a test fills it)."""
    from jobhub_poc.ai import openrouter
    monkeypatch.setattr(openrouter, "_supported", {})
    monkeypatch.setattr(openrouter, "supported", lambda model: openrouter._supported.get(model) if openrouter._supported else None)
