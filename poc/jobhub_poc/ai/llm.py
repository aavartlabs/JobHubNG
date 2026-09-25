"""The LLM the resume and job features use, chosen by AI_BACKEND: "openrouter" (general models
through OpenRouter, ai/openrouter.py) or "ollama" (a server on the LAN, for development,
ai/ollama.py).

Every call says what it carries: task="write" is resume data (parsing, tailoring) and may
only go to providers that don't train on it; task="jobs" is public job text and may also
fall back to direct providers (ai/direct.py) when OpenRouter is down. Same contract either
way: generate() returns a dict matching a JSON schema, temperature 0, and raises
Unavailable when no model can be reached -- the task waits, it doesn't fail. The honesty
checks (resume_parse, job_requirements, tailoring.verify) run on the answer whichever model
gave it."""

SENSITIVE = frozenset({"write"})  # tasks that carry resume data
TASKS = frozenset({"write", "jobs"})

# The model that gave the last answer (the worker is single-threaded), recorded with
# what it produced (job_requirements, tailored_resumes).
_last_model = None


class Unavailable(RuntimeError):
    """Not configured or not reachable right now: queued work waits and is retried."""


def _backend():
    from jobhub_poc import config
    if config.AI_BACKEND == "openrouter":
        from jobhub_poc.ai import openrouter
        return openrouter
    from jobhub_poc.ai import ollama
    return ollama


def available(timeout=3):
    return _backend().available(timeout=timeout)


def generate(prompt, schema, *, timeout=300, task="write"):
    global _last_model
    if task not in TASKS:
        raise ValueError(f"unknown task kind {task!r}")
    backend = _backend()
    if backend.__name__.endswith("ollama"):  # on the LAN: nothing leaves it, whatever the task
        answer = backend.generate(prompt, schema, timeout=timeout)
        _last_model = backend.model_name()
        return answer
    try:
        answer, _last_model = backend.generate(prompt, schema, timeout=timeout, task=task)
    except Unavailable:
        if task in SENSITIVE:
            raise
        from jobhub_poc.ai import direct  # public job text only
        try:
            answer, _last_model = direct.generate(prompt, schema, timeout=timeout, task=task)
        except direct.DirectUnavailable:
            raise Unavailable("OpenRouter and the direct providers are all unavailable") from None
    return answer


def model_name():
    return _last_model or _backend().model_name()
