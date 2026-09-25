"""Cloudflare Workers AI through AI Gateway (AI_BACKEND=workers_ai): JSON mode with the task's
schema, temperature 0. Every request asks the gateway not to log it (`cf-aig-collect-log:
false`): prompts carry resume text. Account, gateway and token come from .env only
(WORKERS_AI_*), never from the repo."""
import json

import requests

from jobhub_poc import config
from jobhub_poc.ai.llm import Unavailable

URL = "https://gateway.ai.cloudflare.com/v1/{account}/{gateway}/workers-ai/{model}"


class WorkersAIUnavailable(Unavailable):
    pass


def _configured():
    return bool(config.WORKERS_AI_ACCOUNT_ID and config.WORKERS_AI_GATEWAY and config.WORKERS_AI_TOKEN)


def available(timeout=3):
    """Configured is enough: a hosted model has no "asleep". A failed call still raises
    WorkersAIUnavailable, so the task waits and is retried."""
    return _configured()


def model_name():
    return config.WORKERS_AI_MODEL


def generate(prompt, schema, *, timeout=300):
    if not _configured():
        raise WorkersAIUnavailable("WORKERS_AI_ACCOUNT_ID / WORKERS_AI_GATEWAY / WORKERS_AI_TOKEN are not set")
    headers = {"Authorization": f"Bearer {config.WORKERS_AI_TOKEN}", "cf-aig-collect-log": "false"}
    if config.WORKERS_AI_GATEWAY_TOKEN:  # an authenticated gateway
        headers["cf-aig-authorization"] = f"Bearer {config.WORKERS_AI_GATEWAY_TOKEN}"
    url = URL.format(account=config.WORKERS_AI_ACCOUNT_ID, gateway=config.WORKERS_AI_GATEWAY,
                     model=config.WORKERS_AI_MODEL)
    try:
        resp = requests.post(url, headers=headers, timeout=timeout, json={
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_schema", "json_schema": schema},
            "temperature": 0, "max_tokens": config.WORKERS_AI_MAX_TOKENS})
    except requests.RequestException as exc:  # never echo the exception: headers hold the token
        raise WorkersAIUnavailable(f"Workers AI unreachable ({type(exc).__name__})") from None
    if resp.status_code == 429 or resp.status_code >= 500:
        raise WorkersAIUnavailable(f"Workers AI busy (HTTP {resp.status_code})")
    if resp.status_code >= 300:
        raise RuntimeError(f"Workers AI returned HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        answer = resp.json()["result"]["response"]
        if isinstance(answer, str):
            answer = json.loads(answer)
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("Workers AI's answer wasn't the JSON asked for") from exc
    if not isinstance(answer, dict):
        raise RuntimeError("Workers AI's answer wasn't a JSON object")
    return answer
