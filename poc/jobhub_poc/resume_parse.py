"""Uploaded resume text -> the structured resume the user reviews and edits (the single
source of truth for matching and tailoring). The writing model only *copies* what is there;
normalise() then keeps it honest: skills must appear in the text, and bullets that don't
appear word-for-word are flagged for the user to check."""
import re

SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "headline": {"type": "string"},
        "location": {"type": "string"},
        "summary": {"type": "string"},
        "skills": {"type": "array", "items": {"type": "string"}},
        "links": {"type": "array", "items": {"type": "string"}},
        "roles": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "company": {"type": "string"}, "location": {"type": "string"},
            "start": {"type": "string"}, "end": {"type": "string"},
            "bullets": {"type": "array", "items": {"type": "string"}}},
            "required": ["title", "company", "start", "end", "bullets"]}},
        "education": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["name", "headline", "summary", "skills", "roles", "education"],
}

PROMPT = """You convert a resume into JSON. Copy, never invent:
- Copy text exactly as written in the resume (fix only line-break hyphenation).
- roles: every job, newest first; bullets = that job's bullet points, copied verbatim.
- skills: only skills/tools/technologies explicitly written in the resume.
- start/end like "2021" or "Mar 2021"; end "Present" if current. Empty string if absent.
- headline: the person's own title line if present, else their most recent job title.
- summary: the resume's own summary/profile paragraph if present, else "".
- Do not include email addresses or phone numbers anywhere.

RESUME:
"""

_WS = re.compile(r"\s+")
_CONTACT = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\+?\d[\d\s().-]{8,}\d")


def _norm(text):
    return _WS.sub(" ", (text or "")).strip()


def _clean(text, limit):
    return _CONTACT.sub("", _norm(text))[:limit].strip()


def normalise(raw: dict, source_text: str) -> dict:
    """The model's answer -> our resume shape: ids on roles/bullets, limits, no contact
    details, skills grounded in the text, ungrounded bullets flagged."""
    haystack = _norm(source_text).lower()
    skills = []
    for s in raw.get("skills") or []:
        s = _clean(s, 60)
        if s and s.lower() in haystack and s.lower() not in (x.lower() for x in skills):
            skills.append(s)
    roles = []
    for i, role in enumerate((raw.get("roles") or [])[:20], 1):
        bullets = []
        for j, b in enumerate((role.get("bullets") or [])[:30], 1):
            text = _clean(b, 400)
            if text:
                bullets.append({"id": f"r{i}b{j}", "text": text,
                                "unverified": text.lower() not in haystack})
        roles.append({
            "id": f"r{i}",
            "title": _clean(role.get("title"), 120), "company": _clean(role.get("company"), 120),
            "location": _clean(role.get("location"), 120),
            "start": _clean(role.get("start"), 20), "end": _clean(role.get("end"), 20),
            "bullets": bullets,
        })
    return {
        "name": _clean(raw.get("name"), 120),
        "headline": _clean(raw.get("headline"), 160),
        "location": _clean(raw.get("location"), 120),
        "summary": _clean(raw.get("summary"), 1200),
        "skills": skills[:60],
        "links": [_norm(u)[:200] for u in (raw.get("links") or [])[:6] if _norm(u)],
        "roles": roles,
        "education": [_clean(e, 200) for e in (raw.get("education") or [])[:10] if _clean(e, 200)],
    }
