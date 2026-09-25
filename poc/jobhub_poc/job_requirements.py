"""What a job asks for, read from its description (job_reading.py: Muse drafts, Jev decides) and cached
per job in job_requirements, for matching.py. Kept honest the same way as resumes: a skill
is kept only if it appears in the job text, and "N+ years" only if the text says so."""
import json
import re
from datetime import datetime, timezone

SENIORITIES = ["intern", "junior", "mid", "senior", "lead", "manager", "director", "unknown"]

SCHEMA = {
    "type": "object",
    "properties": {
        "required_skills": {"type": "array", "items": {"type": "string"}},
        "preferred_skills": {"type": "array", "items": {"type": "string"}},
        "min_years_experience": {"type": ["integer", "null"]},
        "seniority": {"type": "string", "enum": SENIORITIES},
    },
    "required": ["required_skills", "preferred_skills", "min_years_experience", "seniority"],
}

PROMPT = """Read this job posting and list what it asks for. Use only what the text says.
- required_skills: skills, tools, technologies, certifications or domain areas the job requires,
  as SHORT names of 1-4 words copied from the text (e.g. "Kubernetes", "SOX", "Python",
  "financial reporting", "CPA"). Not whole sentences. No soft skills like "communication".
- preferred_skills: the same, for "nice to have" / "preferred" / "bonus" items.
- min_years_experience: the minimum years of experience it asks for, or null if not stated.
- seniority: the level of the role.

TITLE: {title}

POSTING:
{text}
"""


def _norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
          "eleven", "twelve", "thirteen", "fourteen", "fifteen"]


def _says_years(haystack, n):
    """Does the posting state n as a (minimum) number of years? "5+ years", "5 years",
    "5-7 years", "5 to 7 yrs", "five years", "5 or more years"."""
    number = rf"(?:{n}|{_WORDS[n]})" if n < len(_WORDS) else str(n)
    return bool(re.search(
        rf"\b{number}\s*(?:\+|(?:-|–|to)\s*\d+|\(\d+\))?\s*(?:or more\s+|plus\s+)?(?:years?|yrs?)\b", haystack))


def normalise(raw, text):
    """The model's answer -> stored shape, dropping anything the posting doesn't say."""
    haystack = _norm(text).lower()

    def grounded(items):
        out = []
        for item in items or []:
            item = _norm(item).strip(" .;:,")[:50]
            if (item and len(item.split()) <= 5 and item.lower() in haystack
                    and item.lower() not in (x.lower() for x in out)):
                out.append(item)
        return out[:25]

    required = grounded(raw.get("required_skills"))
    preferred = [s for s in grounded(raw.get("preferred_skills")) if s.lower() not in (r.lower() for r in required)]
    years = raw.get("min_years_experience")
    if not (isinstance(years, int) and 0 < years <= 30 and _says_years(haystack, years)):
        years = None
    seniority = raw.get("seniority") if raw.get("seniority") in SENIORITIES else "unknown"
    return {"required_skills": required, "preferred_skills": preferred,
            "min_years": years, "seniority": seniority}


def store(conn, dedupe_key, data, model):
    conn.execute(
        """INSERT INTO job_requirements (job_dedupe_key, data_json, model, extracted_at) VALUES (?, ?, ?, ?)
           ON CONFLICT (job_dedupe_key) DO UPDATE SET data_json = excluded.data_json, model = excluded.model,
             extracted_at = excluded.extracted_at""",
        (dedupe_key, json.dumps(data), model, datetime.now(timezone.utc).isoformat()))
    conn.commit()


def get_many(conn, keys):
    keys = list(keys)
    if not keys:
        return {}
    marks = ",".join("?" * len(keys))
    return {r[0]: json.loads(r[1]) for r in conn.execute(
        f"SELECT job_dedupe_key, data_json FROM job_requirements WHERE job_dedupe_key IN ({marks})", keys)}
