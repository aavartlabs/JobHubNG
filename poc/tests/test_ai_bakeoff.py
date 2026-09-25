"""scripts/ai_bakeoff.py against a stand-in OpenRouter: the site's checks score each model."""
import importlib.util
import json
from pathlib import Path

import pytest

from jobhub_poc import config

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "ai_bakeoff.py"
OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"


@pytest.fixture
def bakeoff(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "or-key")
    spec = importlib.util.spec_from_file_location("ai_bakeoff", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _reply(request, context):
    body = request.json()
    prompt = body["messages"][0]["content"]
    if body["response_format"]["json_schema"]["schema"].get("properties", {}).get("cover_note"):
        # Tailoring: one honest rewrite, one that invents a skill the resume doesn't have.
        answer = {"summary": "", "skills": [], "cover_note": "I would like to apply.",
                  "roles": [{"id": "r1", "bullets": [{"id": "r1b1", "text": "Ran 12 Kubernetes clusters serving 3M daily payments."},
                                                     {"id": "r1b2", "text": "Cut paging noise by 40% with Datadog."}]}]}
    elif "min_years_experience" in json.dumps(body["response_format"]):
        answer = {"required_skills": ["Kubernetes", "Rust"], "preferred_skills": [], "min_years_experience": None, "seniority": "senior"}
    else:
        answer = {"name": "X", "skills": ["Python", "Haskell"], "roles": [{"title": "T", "bullets": ["Wrote Python tooling for backups."]}]}
    return {"model": body["model"], "usage": {"cost": 0.001}, "choices": [{"message": {"content": json.dumps(answer)}}]}


def test_bakeoff_scores_models_with_the_sites_own_checks(bakeoff, requests_mock, capsys):
    requests_mock.post(OPENROUTER, json=_reply)
    report = bakeoff.main(["--write-models", "openai/test-a", "--jobs-models", "meta/test-contributor"])
    tailor, parse, jobs = report["tailor  openai/test-a"], report["parse   openai/test-a"], report["jobs    meta/test-contributor"]
    assert tailor["cases"] == 16 and tailor["failed"] == 0 and tailor["leftover"] == 0
    assert tailor["caught"] >= 1  # the Datadog rewrite was put back where the resume lacks it
    # "Haskell" in no resume (4) + "Python" in the two resumes without it (2).
    assert parse["cases"] == 4 and parse["invented_skills"] == 6
    # "Rust" in no posting (4) + "Kubernetes" in the three postings without it (3).
    assert jobs["cases"] == 4 and jobs["invented_skills"] == 7 and jobs["skills_kept"] == 1
    assert tailor["cost_usd"] == pytest.approx(0.016)
    sent = [r.json() for r in requests_mock.request_history]
    assert all(r["provider"].get("data_collection") == "deny" for r in sent if r["model"] == "openai/test-a")


def test_bakeoff_never_sends_resumes_to_a_training_model(bakeoff, requests_mock):
    requests_mock.post(OPENROUTER, json=_reply)
    report = bakeoff.main(["--write-models", "meta/muse-spark-1.3-contributor"])
    assert report["tailor  meta/muse-spark-1.3-contributor"]["failed"] == 16
    assert requests_mock.call_count == 0
