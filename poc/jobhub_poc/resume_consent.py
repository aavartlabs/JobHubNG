"""What a user agrees to before JobsHub's AI reads their resume. The words depend on where the
model runs (AI_BACKEND): when that changes, consent given to the old words stops counting and
the user is asked again on /profile before any more AI work on their resume (upload parsing,
tailoring). A consent is current if it was given on or after the backend's `since`
(RESUME_CONSENT_SINCE overrides it -- set it to the cutover time when switching)."""
from jobhub_poc import config

_TERMS = {
    "ollama": ("", "JobsHub stores my resume (encrypted) and uses it to match me with jobs and to "
                   "tailor it for jobs I choose. It's processed on JobsHub's own machines, not sent "
                   "to other companies, and I can delete it any time."),
    "workers_ai": ("2026-09-25", "JobsHub stores my resume (encrypted) and uses it to match me with "
                                 "jobs and to tailor it for jobs I choose. To do that, its text is read "
                                 "by an AI model that JobsHub runs on Cloudflare's Workers AI service. "
                                 "It isn't shared with employers or anyone else, and I can delete it any time."),
}


def _terms():
    return _TERMS.get(config.AI_BACKEND, _TERMS["ollama"])


def text():
    return _terms()[1]


def since():
    return config.RESUME_CONSENT_SINCE or _terms()[0]


def is_current(consent_at):
    """ISO timestamps compare as strings; a bare date `since` means from that day on."""
    return bool(consent_at) and consent_at >= since()


class ConsentNeeded(RuntimeError):
    """The owner hasn't agreed to the current terms: no AI work on their resume."""
