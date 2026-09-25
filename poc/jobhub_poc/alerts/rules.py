"""What an alert asks for, and whether a job matches it. Pure; no database.

OR within a filter, AND across filters: titles ("SRE", "DevOps") AND locations
("Bangalore", "Remote") AND ... Empty filters are ignored, but a rule with no filters at
all matches nothing -- a filterless alert must never mean "every job".

Terms match whole words, case-insensitively: "java" doesn't match "JavaScript", "sre"
doesn't match "Treasurer". Locations also match their other names, and "India" its cities
(places.py).
"""
import re
from dataclasses import dataclass
from functools import lru_cache

from jobhub_poc import places

@dataclass(frozen=True)
class Rule:
    titles: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    companies: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    work_mode: str | None = None  # "remote" | "onsite" | None (any)

    def is_empty(self):
        return not (self.titles or self.locations or self.companies or self.keywords or self.work_mode)


@lru_cache(maxsize=4096)
def _word(term):
    # (?<!\w)/(?!\w) rather than \b, so terms ending in punctuation ("c++") still match.
    return re.compile(r"(?<!\w)" + re.escape(term.strip()) + r"(?!\w)", re.IGNORECASE)


def _any_word(terms, text):
    return bool(text) and any(_word(t).search(text) for t in terms)


def _is_remote(job):
    return bool(job.get("is_remote")) or _any_word(("remote",), job.get("location") or "")


def _location_matches(wanted, job):
    location = job.get("location") or ""
    for term in wanted:
        term = term.strip().lower()
        term = places.correct(term) or term  # "Bengluru" -> "bengaluru"
        if term == "remote" and _is_remote(job):
            return True
        if _any_word(places.spellings(term), location):
            return True
    return False


def rule_matches(rule, job):
    if rule.is_empty():
        return False
    if rule.titles and not _any_word(rule.titles, job.get("title") or ""):
        return False
    if rule.locations and not _location_matches(rule.locations, job):
        return False
    if rule.companies and not _any_word(rule.companies, job.get("company_name") or ""):
        return False
    if rule.keywords and not _any_word(
        rule.keywords, f"{job.get('title') or ''}\n{job.get('description') or ''}"
    ):
        return False
    if rule.work_mode == "remote" and not _is_remote(job):
        return False
    if rule.work_mode == "onsite" and _is_remote(job):
        return False
    return True
