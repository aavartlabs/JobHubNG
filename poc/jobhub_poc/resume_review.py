"""What in a structured resume probably needs the user's attention, section by section, with
concrete suggestions. Deterministic rules (no LLM): shown on /profile to help people check
what was read from their file. Suggestions never invent facts -- they point at gaps, or
offer a value that already exists elsewhere in the resume (e.g. the latest job title)."""
import re

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_CURRENT = {"present", "current", "now", "till date", "to date", "ongoing"}


def parse_month(value):
    """(year, month) from "2021", "Mar 2021", "March 2021", "03/2021", "2021-03"; the string
    "present" for current roles; None if empty; "bad" if it can't be read."""
    v = (value or "").strip().lower()
    if not v:
        return None
    if v in _CURRENT:
        return "present"
    m = re.fullmatch(r"(19|20)\d{2}", v)
    if m:
        return (int(v), 1)
    m = re.fullmatch(r"([a-z]{3,9})\.?\s+((?:19|20)\d{2})", v)
    if m and m.group(1)[:3] in _MONTHS:
        return (int(m.group(2)), _MONTHS[m.group(1)[:3]])
    m = re.fullmatch(r"(\d{1,2})[/.-]((?:19|20)\d{2})", v) or None
    if m and 1 <= int(m.group(1)) <= 12:
        return (int(m.group(2)), int(m.group(1)))
    m = re.fullmatch(r"((?:19|20)\d{2})[/.-](\d{1,2})", v)
    if m and 1 <= int(m.group(2)) <= 12:
        return (int(m.group(1)), int(m.group(2)))
    return "bad"


def _item(level, message, fill=None):
    """level: "fix" (likely wrong/missing and it matters) or "check" (worth a look)."""
    out = {"level": level, "message": message}
    if fill:
        out["fill"] = fill  # {"field": form field name, "value": suggested value}
    return out


def review(s):
    """{section key: [items]} for sections with something to say; role sections are
    "role-<index>" matching the form's role blocks."""
    s = s or {}
    notes = {}
    roles = s.get("roles") or []
    latest_title = next((r.get("title") for r in roles if r.get("title")), "")

    basics = []
    if not s.get("name"):
        basics.append(_item("fix", "Add your name."))
    if not s.get("headline"):
        basics.append(_item("fix", "Add a headline — usually your current job title.",
                            {"field": "headline", "value": latest_title} if latest_title else None))
    if not s.get("location"):
        basics.append(_item("check", "Add your city (and country): it's used to match jobs near you."))
    if basics:
        notes["basics"] = basics

    summary = (s.get("summary") or "").strip()
    if not summary:
        notes["summary"] = [_item("check", "No summary was found. Two or three sentences on what you do "
                                           "and your strongest areas help recruiters — use only what's in your experience.")]
    elif len(summary) < 80:
        notes["summary"] = [_item("check", "Your summary is very short; a couple of sentences about your "
                                           "experience and strengths work better.")]

    skills = s.get("skills") or []
    if not skills:
        notes["skills"] = [_item("fix", "No skills were found. Add the tools and skills you actually use — "
                                        "they drive job matching.")]
    elif len(skills) < 5:
        notes["skills"] = [_item("check", f"Only {len(skills)} skill{'s' if len(skills) != 1 else ''} found. "
                                          "Add any others you use (tools, languages, platforms).")]

    if not roles:
        notes["experience"] = [_item("fix", "No work experience was found. Add your roles below — "
                                            "they're what matching and tailoring use.")]
    for i, role in enumerate(roles):
        items = []
        if not role.get("title") or not role.get("company"):
            items.append(_item("fix", "Add both the job title and the company."))
        start, end = parse_month(role.get("start")), parse_month(role.get("end"))
        if start is None or end is None:
            items.append(_item("fix", "Add start and end dates (e.g. \"Mar 2021\", or \"Present\") — "
                                      "they're used to count your years of experience."))
        if start == "bad" or end == "bad":
            items.append(_item("fix", "Use a date like \"Mar 2021\", \"2021\" or \"Present\"."))
        if start == "present":
            items.append(_item("fix", "The start date says \"Present\" — use the month you started."))
        if isinstance(start, tuple) and isinstance(end, tuple) and end < start:
            items.append(_item("fix", "The end date is before the start date."))
        bullets = role.get("bullets") or []
        if not bullets:
            items.append(_item("check", "No bullet points. Add 2–4 lines on what you did and achieved."))
        flagged = [b["text"] for b in bullets if b.get("unverified")]
        for text in flagged:
            short = text if len(text) <= 70 else text[:67] + "…"
            items.append(_item("check", f"“{short}” wasn't found word-for-word in your file — check it's right."))
        if items:
            notes[f"role-{i}"] = items

    if not s.get("education"):
        notes["education"] = [_item("check", "No education was found. Add your highest qualification if you have one.")]
    return notes


def count(notes):
    return sum(len(v) for v in notes.values())
