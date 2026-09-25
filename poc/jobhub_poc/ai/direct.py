"""LLMs called directly on their own APIs (not through OpenRouter), for **public job postings
only**: they may keep and train on what they're sent (Meta's "-contributor" tier is priced on
exactly that), so resume data never comes here -- ask() and generate() refuse any task but
"jobs". A provider appears in AI_MODELS_JOBS as "direct:<name>" (e.g. Meta's Muse Spark
contributor tier, first in the chain), and DIRECT_JOBS_PROVIDERS are the last resort when
OpenRouter itself is unavailable.

Each provider is an OpenAI-compatible chat endpoint configured in .env:
<NAME>_API_KEY, <NAME>_BASE_URL, <NAME>_MODEL, and optionally <NAME>_JSON ("schema" to send
the task's JSON schema, else the plain json_object mode with the schema in the prompt) and
<NAME>_REASONING_EFFORT (e.g. "minimal": Meta's Muse answers a job read in about 2 s instead
of 7 s). A provider missing any of the first three is skipped."""
import json
import os

import requests

from jobhub_poc import config
from jobhub_poc.ai.llm import Unavailable

DEFAULTS = {"deepseek": {"BASE_URL": "https://api.deepseek.com", "MODEL": "deepseek-chat"}}


class DirectUnavailable(Unavailable):
    pass


def _settings(name, env):
    prefix = name.upper()
    get = lambda key: env.get(f"{prefix}_{key}") or DEFAULTS.get(name, {}).get(key, "")  # noqa: E731
    values = {key: get(key) for key in ("API_KEY", "BASE_URL", "MODEL", "JSON", "REASONING_EFFORT")}
    return values if all(values[k] for k in ("API_KEY", "BASE_URL", "MODEL")) else None


def providers(env=os.environ):
    return [(name, s) for name in config.DIRECT_JOBS_PROVIDERS if (s := _settings(name, env))]


def _refuse_unless_public(task):
    if task != "jobs":
        raise RuntimeError(f"direct providers only take public job text, not {task!r} tasks")


def ask(name, prompt, schema, *, timeout=300, task="jobs", env=os.environ):
    """One provider, one try: (answer, "<name>/<model>"). DirectUnavailable when it's
    unreachable or busy; RuntimeError when it answered badly or isn't configured."""
    _refuse_unless_public(task)
    p = _settings(name, env)
    if p is None:
        raise RuntimeError(f"direct provider {name!r} isn't configured ({name.upper()}_API_KEY/_BASE_URL/_MODEL)")
    body = {"model": p["MODEL"], "temperature": 0}
    if p["JSON"] == "schema":
        body["messages"] = [{"role": "user", "content": prompt}]
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": "answer", "schema": schema}}
    else:
        content = f"{prompt}\n\nAnswer with one JSON object matching this JSON schema:\n{json.dumps(schema)}"
        body["messages"] = [{"role": "user", "content": content}]
        body["response_format"] = {"type": "json_object"}
    if p["REASONING_EFFORT"]:
        body["reasoning_effort"] = p["REASONING_EFFORT"]
    try:
        resp = requests.post(f"{p['BASE_URL'].rstrip('/')}/chat/completions", timeout=timeout,
                             headers={"Authorization": f"Bearer {p['API_KEY']}"}, json=body)
    except requests.RequestException as exc:  # never echo it: the headers hold the key
        raise DirectUnavailable(f"{name}: unreachable ({type(exc).__name__})") from None
    if resp.status_code in (408, 429) or resp.status_code >= 500:
        raise DirectUnavailable(f"{name}: HTTP {resp.status_code}")
    if resp.status_code >= 300:
        raise RuntimeError(f"{name}: HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        answer = json.loads(resp.json()["choices"][0]["message"]["content"])
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"{name}: answer wasn't JSON") from exc
    if not isinstance(answer, dict):
        raise RuntimeError(f"{name}: answer wasn't a JSON object")
    return answer, f"{name}/{p['MODEL']}"


def generate(prompt, schema, *, timeout=300, task="jobs", env=os.environ):
    """The last resort: each of DIRECT_JOBS_PROVIDERS in turn. (answer, "<name>/<model>")."""
    _refuse_unless_public(task)
    configured = providers(env)
    if not configured:
        raise DirectUnavailable("no direct providers configured")
    problems = []
    for name, _settings_ in configured:
        try:
            return ask(name, prompt, schema, timeout=timeout, task=task, env=env)
        except (DirectUnavailable, RuntimeError) as exc:
            problems.append(str(exc))
    raise DirectUnavailable("; ".join(problems))
