"""TypeSafe's Jev: fast judgments (choice / noul / score with probabilities), not text. Used
wherever the AI decides something (job_reading.py, match_evidence.py); the question sets
live in ai/judgments.py. One request asks many questions about one state at once.

Jev doesn't train on requests. It may see resume text (matching), which the resume consent
names (resume_consent.py). Key: TYPESAFE_API_KEY in .env."""
import requests

from jobhub_poc import config
from jobhub_poc.ai.llm import Unavailable

URL = "https://api.typesafe.ai/v1/systemone"


class TypeSafeUnavailable(Unavailable):
    pass


def available():
    return bool(config.TYPESAFE_API_KEY) and not config.AI_PAUSED


def ask(state, questions, *, timeout=60):
    """{question id: answer} for `questions` (ai/judgments.py shapes) about `state`.
    TypeSafeUnavailable when it can't answer now (unset key, network, 429/529/5xx: the task
    waits); RuntimeError when the request itself is wrong (the task fails)."""
    if not config.TYPESAFE_API_KEY:
        raise TypeSafeUnavailable("TYPESAFE_API_KEY is not set")
    if config.AI_PAUSED:
        raise TypeSafeUnavailable("AI is paused (AI_PAUSED=1)")
    try:
        resp = requests.post(URL, timeout=timeout, headers={"Authorization": f"Bearer {config.TYPESAFE_API_KEY}"},
                             json={"model": config.TYPESAFE_MODEL, "state": state, "questions": questions})
    except requests.RequestException as exc:  # never echo it: the headers hold the key
        raise TypeSafeUnavailable(f"TypeSafe unreachable ({type(exc).__name__})") from None
    if resp.status_code in (408, 429, 529) or resp.status_code >= 500:
        raise TypeSafeUnavailable(f"TypeSafe busy (HTTP {resp.status_code})")
    if resp.status_code == 401:
        raise TypeSafeUnavailable("TypeSafe rejected the API key (HTTP 401)")
    if resp.status_code >= 300:
        raise RuntimeError(f"TypeSafe returned HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        answers = resp.json()["answers"]
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("TypeSafe's answer wasn't the shape expected") from exc
    missing = [q for q in questions if q not in answers]
    if missing:
        raise RuntimeError(f"TypeSafe didn't answer {len(missing)} question(s)")
    return answers
