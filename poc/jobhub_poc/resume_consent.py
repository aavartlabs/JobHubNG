"""What a user agrees to before JobsHub's AI reads their resume. The words depend on where the
models run (AI_BACKEND) and whether Jev (TypeSafe) is on: when that changes, consent given to the old words stops counting and
the user is asked again on /profile before any more AI work on their resume (parsing,
matching, tailoring). A consent is current if it was given on or after the backend's `since`
(RESUME_CONSENT_SINCE overrides it -- set it to the moment AI_BACKEND changes)."""
from jobhub_poc import config

_TERMS = {
    "ollama": ("", "JobsHub stores my resume (encrypted) and uses it to match me with jobs and to "
                   "tailor it for jobs I choose. It's processed on JobsHub's own machines, not sent "
                   "to other companies, and I can delete it any time."),
    "openrouter": ("2026-09-25", "JobsHub stores my resume (encrypted) and uses it to match me with "
                                 "jobs and to tailor it for jobs I choose. To do that, its text is read by "
                                 "AI services JobsHub uses (TypeSafe, and language models reached through "
                                 "OpenRouter) that don't train on it. It isn't shared with employers or "
                                 "anyone else, and I can delete it any time."),
}


# The local model with Jev on (TYPESAFE_API_KEY set): match evidence sends the work history and
# skills -- never the name, contact details or links (match_evidence.state_for_jev) -- to TypeSafe.
# Turning it on for existing users: set RESUME_CONSENT_SINCE to that moment (the date below is
# only the earliest these words existed).
_OLLAMA_WITH_JEV = ("2026-09-25", "JobsHub stores my resume (encrypted) and uses it to match me with jobs and "
                                  "to tailor it for jobs I choose. It's read on JobsHub's own machines; to judge how "
                                  "well I fit a job, my work history and skills (not my name or contact details) are "
                                  "also checked by TypeSafe, an AI service that doesn't train on them. It isn't shared "
                                  "with employers or anyone else, and I can delete it any time.")


def _terms():
    if config.AI_BACKEND not in _TERMS or config.AI_BACKEND == "ollama":
        return _OLLAMA_WITH_JEV if config.TYPESAFE_API_KEY else _TERMS["ollama"]
    return _TERMS[config.AI_BACKEND]


def text():
    return _terms()[1]


def since():
    return config.RESUME_CONSENT_SINCE or _terms()[0]


def is_current(consent_at):
    """ISO timestamps compare as strings; a bare date `since` means from that day on."""
    return bool(consent_at) and consent_at >= since()


class ConsentNeeded(RuntimeError):
    """The owner hasn't agreed to the current terms: no AI work on their resume."""
