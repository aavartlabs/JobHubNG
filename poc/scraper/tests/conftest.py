import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def _no_live_job_board_apis(monkeypatch):
    """ingest.main fetches the [sources] APIs; tests never reach the real ones."""
    import ingest
    monkeypatch.setattr(ingest, "_fetch_from_sources", lambda cfg: ([], {}))
