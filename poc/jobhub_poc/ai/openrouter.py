"""General LLMs through OpenRouter (AI_BACKEND=openrouter): one key, many models, tried in
order per task (AI_MODELS_WRITE / AI_MODELS_JOBS). JSON out against the task's schema,
temperature 0.

Resume data ("write" tasks) may only reach providers that don't train on it: every such
request carries provider.data_collection = "deny" (plus zdr when OPENROUTER_ZDR is on), and
models whose price is paid in training rights (e.g. Meta's "-contributor" tier) are refused
here, whatever the config says. Public job postings ("jobs") may use any model.

ai/llm.py walks the chain: a model that's busy, down or answers with something that isn't
the JSON asked for is skipped for the next one."""
import json
import re

import requests

from jobhub_poc import config
from jobhub_poc.ai.llm import SENSITIVE, Unavailable

URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS_URL = "https://openrouter.ai/api/v1/models"
_supported = {}  # model -> the request parameters it accepts (OpenRouter's public model list)
# Models that pay for their price with the right to train on prompts and outputs.
TRAINS_ON_PROMPTS = re.compile(r"-contributor(\b|$)|:free$")


class OpenRouterUnavailable(Unavailable):
    pass


class _BadAnswer(RuntimeError):
    pass


def chain(task):
    models = config.AI_MODELS_WRITE if task in SENSITIVE else config.AI_MODELS_JOBS
    models = [m for m in models if m]
    if task in SENSITIVE:
        refused = [m for m in models if TRAINS_ON_PROMPTS.search(m) or m.startswith("direct:")]
        if refused:
            raise RuntimeError(f"refusing to send resume data to {', '.join(refused)}: "
                               "it trains on prompts or is a direct provider (public job text only)")
    return models


def supported(model):
    """The parameters `model` accepts, or None if the list can't be fetched. Fetched once per
    process: with require_parameters, sending one a model lacks (e.g. temperature to a
    reasoning model) leaves no provider to serve it."""
    if not _supported:
        try:
            resp = requests.get(MODELS_URL, timeout=10)
            resp.raise_for_status()
            _supported.update({m["id"]: set(m.get("supported_parameters") or []) for m in resp.json()["data"]})
        except (requests.RequestException, ValueError, KeyError, TypeError):
            return None
    return _supported.get(model)


def available(timeout=3):
    return bool(config.OPENROUTER_API_KEY and config.AI_MODELS_WRITE)


def model_name():
    models = chain("write")
    return models[0] if models else ""



def ask(model, prompt, schema, task, timeout):
    """One model, one try: (answer, the model that served it, usage incl. cost in USD)."""
    if task in SENSITIVE and TRAINS_ON_PROMPTS.search(model):
        raise RuntimeError(f"refusing to send resume data to {model}: it trains on prompts")
    if not config.OPENROUTER_API_KEY:
        raise OpenRouterUnavailable("OPENROUTER_API_KEY is not set")
    provider = {"require_parameters": True}
    if task in SENSITIVE:
        provider["data_collection"] = "deny"
        if config.OPENROUTER_ZDR:
            provider["zdr"] = True
    params = supported(model)
    extra = {}
    if params is None or "temperature" in params:
        extra["temperature"] = 0
    if config.AI_REASONING_EFFORT and params and "reasoning" in params:
        extra["reasoning"] = {"effort": config.AI_REASONING_EFFORT}
    try:
        resp = requests.post(URL, timeout=timeout, headers={
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}", "X-Title": "JobsHub"}, json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "answer", "strict": config.OPENROUTER_STRICT, "schema": schema}},
            "max_tokens": config.AI_MAX_TOKENS, "provider": provider, "usage": {"include": True}, **extra})
    except requests.RequestException as exc:  # never echo it: the headers hold the key
        raise OpenRouterUnavailable(f"{model}: unreachable ({type(exc).__name__})") from None
    if resp.status_code in (402, 408, 429) or resp.status_code >= 500:
        raise OpenRouterUnavailable(f"{model}: HTTP {resp.status_code}")
    if resp.status_code >= 300:
        raise _BadAnswer(f"{model}: HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        body = resp.json()
        content = body["choices"][0]["message"]["content"]
        answer = json.loads(content) if isinstance(content, str) else content
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise _BadAnswer(f"{model}: answer wasn't the JSON asked for") from exc
    if not isinstance(answer, dict):
        raise _BadAnswer(f"{model}: answer wasn't a JSON object")
    return answer, body.get("model") or model, body.get("usage") or {}
