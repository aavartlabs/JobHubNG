"""The local LLM (Ollama on the LAN, OLLAMA_URL / OLLAMA_MODEL). JSON out only: every call
passes a JSON schema as Ollama's `format`, temperature 0. Resumes never leave the LAN."""
import json

import requests

from jobhub_poc import config
from jobhub_poc.ai.llm import Unavailable


class OllamaUnavailable(Unavailable):
    """Not configured or not reachable (e.g. harita asleep): the task should wait, not fail."""


def available(timeout=3):
    if not config.OLLAMA_URL:
        return False
    try:
        return requests.get(f"{config.OLLAMA_URL.rstrip('/')}/api/version", timeout=timeout).ok
    except requests.RequestException:
        return False


def model_name():
    return config.OLLAMA_MODEL


def generate(prompt, schema, *, model=None, timeout=300):
    """The model's answer as a dict matching `schema` (Ollama structured output)."""
    if not config.OLLAMA_URL:
        raise OllamaUnavailable("OLLAMA_URL is not set")
    try:
        resp = requests.post(
            f"{config.OLLAMA_URL.rstrip('/')}/api/generate",
            # think=False: "thinking" models (qwen3) otherwise spend the answer on reasoning and
            # return broken JSON; models without thinking (gemma4) ignore it.
            json={"model": model or config.OLLAMA_MODEL, "prompt": prompt, "format": schema,
                  "stream": False, "think": False,
                  "options": {"temperature": 0, **({"num_ctx": config.OLLAMA_NUM_CTX} if config.OLLAMA_NUM_CTX else {})}},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise OllamaUnavailable(f"Ollama unreachable ({type(exc).__name__})") from exc
    if resp.status_code >= 300:
        raise RuntimeError(f"Ollama returned HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        answer = json.loads(resp.json()["response"])
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("Ollama's answer wasn't the JSON asked for") from exc
    if not isinstance(answer, dict):
        raise RuntimeError("Ollama's answer wasn't a JSON object")
    return answer
