"""What a user agrees to before JobsHub's AI reads their resume. When the wording changes,
consent given to the old words stops counting and the user is asked again on /profile before
any more AI work on their resume (parsing, matching, tailoring). A consent is current if it
was given on or after SINCE (RESUME_CONSENT_SINCE overrides it: set it to the moment the new
wording went live)."""
from jobhub_poc import config

TEXT = ("JobsHub stores my resume (encrypted) and uses it to match me with jobs and to tailor it "
        "for jobs I choose. To do that, its text is read by AI services JobsHub uses (TypeSafe, and "
        "language models reached through OpenRouter) that don't train on it. It isn't shared with "
        "employers or anyone else, and I can delete it any time.")
SINCE = "2026-09-25"  # the wording above replaced "processed on JobsHub's own machines"


def text():
    return TEXT


def since():
    return config.RESUME_CONSENT_SINCE or SINCE


def is_current(consent_at):
    """ISO timestamps compare as strings; a bare date `since` means from that day on."""
    return bool(consent_at) and consent_at >= since()


class ConsentNeeded(RuntimeError):
    """The owner hasn't agreed to the current terms: no AI work on their resume."""
