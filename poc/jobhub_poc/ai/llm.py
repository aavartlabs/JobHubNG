"""The LLM the resume features use, chosen by AI_BACKEND: "ollama" (a server on the LAN,
ai/ollama.py) or "workers_ai" (Cloudflare Workers AI through AI Gateway, ai/workers_ai.py).
Same contract either way: generate() returns a dict matching a JSON schema, temperature 0,
and raises Unavailable when the model can't be reached -- the task waits, it doesn't fail.
The honesty checks (resume_parse, job_requirements, tailoring.verify) run on the answer
whichever model gave it."""


class Unavailable(RuntimeError):
    """Not configured or not reachable right now: queued work waits and is retried."""


def _backend():
    from jobhub_poc import config
    if config.AI_BACKEND == "workers_ai":
        from jobhub_poc.ai import workers_ai
        return workers_ai
    from jobhub_poc.ai import ollama
    return ollama


def available(timeout=3):
    return _backend().available(timeout=timeout)


def generate(prompt, schema, *, timeout=300):
    return _backend().generate(prompt, schema, timeout=timeout)


def model_name():
    """Recorded with what the model produced (job_requirements, tailored_resumes)."""
    return _backend().model_name()
