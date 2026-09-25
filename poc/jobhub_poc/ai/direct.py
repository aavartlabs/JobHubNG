"""Last-resort LLMs called directly (not through OpenRouter), for **public job postings
only**: they keep and may train on what they're sent, so resume data never comes here --
generate() refuses any task but "jobs". Used when OpenRouter itself is unavailable.

Each provider is an OpenAI-compatible chat endpoint configured in .env:
<NAME>_API_KEY, <NAME>_BASE_URL, <NAME>_MODEL, for the names in DIRECT_JOBS_PROVIDERS
(e.g. "deepseek,meta"). A provider missing any of the three is skipped. JSON mode is the
plain json_object kind (not every such API takes a schema), so the schema goes in the
prompt and the answer is checked downstream like any other."""
import json
import os

import requests

from jobhub_poc import config
from jobhub_poc.ai.llm import Unavailable

DEFAULTS = {"deepseek": {"BASE_URL": "https://api.deepseek.com", "MODEL": "deepseek-chat"}}


class DirectUnavailable(Unavailable):
    pass


def providers(env=os.environ):
    found = []
    for name in config.DIRECT_JOBS_PROVIDERS:
        prefix = name.upper()
        values = {key: env.get(f"{prefix}_{key}") or DEFAULTS.get(name, {}).get(key, "")
                  for key in ("API_KEY", "BASE_URL", "MODEL")}
        if all(values.values()):
            found.append((name, values))
    return found


def generate(prompt, schema, *, timeout=300, task="jobs", env=os.environ):
    """(answer, "<provider>/<model>")."""
    if task != "jobs":
        raise RuntimeError(f"direct providers only take public job text, not {task!r} tasks")
    configured = providers(env)
    if not configured:
        raise DirectUnavailable("no direct providers configured")
    content = f"{prompt}\n\nAnswer with one JSON object matching this JSON schema:\n{json.dumps(schema)}"
    problems = []
    for name, p in configured:
        try:
            resp = requests.post(f"{p['BASE_URL'].rstrip('/')}/chat/completions", timeout=timeout,
                                 headers={"Authorization": f"Bearer {p['API_KEY']}"},
                                 json={"model": p["MODEL"], "messages": [{"role": "user", "content": content}],
                                       "response_format": {"type": "json_object"}, "temperature": 0})
        except requests.RequestException as exc:  # never echo it: the headers hold the key
            problems.append(f"{name}: unreachable ({type(exc).__name__})")
            continue
        if resp.status_code >= 300:
            problems.append(f"{name}: HTTP {resp.status_code}")
            continue
        try:
            answer = json.loads(resp.json()["choices"][0]["message"]["content"])
        except (ValueError, KeyError, IndexError, TypeError):
            problems.append(f"{name}: answer wasn't JSON")
            continue
        if isinstance(answer, dict):
            return answer, f"{name}/{p['MODEL']}"
        problems.append(f"{name}: answer wasn't a JSON object")
    raise DirectUnavailable("; ".join(problems))
