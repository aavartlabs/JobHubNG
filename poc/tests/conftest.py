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
