"""The general (writing) LLMs the resume and job features use, through OpenRouter
(ai/openrouter.py) and, for public job text only, providers' own APIs (ai/direct.py).
Judgments are Jev's (ai/typesafe.py), not these.

Every call says what it carries: task="write" is resume data (parsing, tailoring) and may
only go to providers that don't train on it; task="jobs" is public job text and may also
fall back to direct providers (ai/direct.py) when OpenRouter is down. Same contract either
way: generate() returns a dict matching a JSON schema, temperature 0, and raises
Unavailable when no model can be reached -- the task waits, it doesn't fail. The honesty
checks (resume_parse, job_requirements, tailoring.verify) run on the answer whichever model
gave it."""

import threading

SENSITIVE = frozenset({"write"})  # tasks that carry resume data
TASKS = frozenset({"write", "jobs"})

# The model that gave this thread's last answer, recorded with what it produced
# (job_requirements, tailored_resumes). Per thread: the worker runs several at once.
_state = threading.local()


class Unavailable(RuntimeError):
    """Not configured or not reachable right now: queued work waits and is retried."""


def _backend():
    from jobhub_poc.ai import openrouter
    return openrouter


def available(timeout=3):
    return _backend().available(timeout=timeout)


def generate(prompt, schema, *, timeout=300, task="write"):
    if task not in TASKS:
        raise ValueError(f"unknown task kind {task!r}")
    backend = _backend()
    from jobhub_poc.ai import direct
    # The chain for this task, in order: OpenRouter models, and (public job text only)
    # "direct:<name>" providers. chain() refuses a resume chain that names anything that
    # trains on prompts or a direct provider.
    busy, bad = [], []
    for entry in backend.chain(task):
        try:
            if entry.startswith("direct:"):
                answer, _state.model = direct.ask(entry.split(":", 1)[1], prompt, schema, timeout=timeout, task=task)
            else:
                answer, _state.model, _usage = backend.ask(entry, prompt, schema, task, timeout)
            return answer
        except Unavailable as exc:
            busy.append(str(exc))
        except RuntimeError as exc:
            bad.append(str(exc))
    if not busy and not bad:
        raise Unavailable(f"no models configured for {task} tasks")
    if bad:
        raise RuntimeError("; ".join(bad + busy))
    if task in SENSITIVE:
        raise Unavailable("; ".join(busy))
    try:  # public job text: the last-resort direct providers
        answer, _state.model = direct.generate(prompt, schema, timeout=timeout, task=task)
        return answer
    except direct.DirectUnavailable:
        raise Unavailable("every model and direct provider is unavailable: " + "; ".join(busy)) from None


def model_name():
    return getattr(_state, "model", None) or _backend().model_name()
