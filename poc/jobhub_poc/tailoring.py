"""Honest tailoring: the user's checked resume, reorganised for one job.

The writing model may only *select, reorder and lightly reword* what is already in the resume,
and draft a short cover note from it. It never decides what is true: verify() -- plain code
-- checks every fact the model wrote against the resume and puts the original wording back
wherever it can't be found there. Per piece of text:

- numbers ("40%", "3", "2019") must appear in the source (the bullet it rewrites; for the
  summary and cover note, anywhere in the resume);
- capitalised names and tools (Kubernetes, Acme, AWS) must appear in the source too;
- none of the job's own skills may appear unless the source already has them -- the easy
  way for a model to "tailor" is to copy the job ad into the resume, and that is the lie
  this module exists to stop.

Roles are never dropped, renamed or reordered (that would change the work history); the
headline stays the user's own. Skills are only reordered, never added."""
import json
import re

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "roles": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"},
            "bullets": {"type": "array", "items": {"type": "object", "properties": {
                "id": {"type": "string"}, "text": {"type": "string"}}, "required": ["id", "text"]}}},
            "required": ["id", "bullets"]}},
        "skills": {"type": "array", "items": {"type": "string"}},
        "cover_note": {"type": "string"},
    },
    "required": ["summary", "roles", "skills", "cover_note"],
}

PROMPT = """You help a candidate present their REAL experience for one job.
Use ONLY facts written in RESUME. Never add a skill, tool, number, employer, title or result
that is not there. If the job asks for something the resume doesn't show, leave it out --
do not mention it at all.

- roles: for EVERY role id, list that role's bullets that matter for this job (by id), most
  relevant first, at most 5. Leave out bullets that don't help with this job (hobbies,
  unrelated duties). You may lightly reword a bullet so its relevance is clearer, keeping
  every fact and number exactly as written. Never merge bullets.
- skills: the resume's skills, the ones this job asks for first. Only skills from RESUME.
- summary: 2-3 sentences in the candidate's voice (no "I"), built only from the resume,
  leading with what matters most for this job.
- cover_note: 80-120 words, first person ("I ..."), to the hiring team for this job. Say why
  the candidate's actual experience fits, citing 2-3 concrete results from the resume. Do not
  just list the bullets. No greeting line and no sign-off.

JOB: {title} at {company}
WHAT THE JOB ASKS FOR: {asks}

RESUME (JSON, bullet ids like r1b2):
{resume}
"""

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
# Capitalised words and tool-like tokens (AWS, CI/CD, Node.js, C++).
_TERM = re.compile(r"(?<![\w.])([A-Z][\w+#./-]*[\w+#]|[A-Z]{2,}|[A-Z])(?![\w])")
# Capitalised only because of grammar (sentence starts, pronouns), not claims.
_STOP = {
    "I", "I'm", "I've", "A", "An", "The", "My", "Me", "We", "Our", "They", "Their", "He", "She", "His", "Her", "In", "On", "At", "For", "With", "As", "And", "By",
    "To", "From", "Over", "Across", "Having", "This", "That", "These", "Your", "You", "It", "Its",
    "Led", "Built", "Ran", "Owned", "Drove", "Delivered", "Designed", "Developed", "Managed",
    "Improved", "Reduced", "Increased", "Created", "Implemented", "Worked", "Migrated", "Cut",
    "Mentored", "Automated", "Launched", "Maintained", "Supported", "Helped", "Wrote", "Grew",
    "Shipped", "Scaled", "Handled", "Partnered", "Collaborated", "Introduced", "Established",
    "Responsible", "Experienced", "Skilled", "Proven", "Seasoned", "Passionate", "Strong",
    "Currently", "Previously", "Thank", "Thanks", "Hello", "Dear", "Regards", "Best", "Sincerely",
    "Hands-on", "Also", "Most", "Recently", "Today", "Now", "Here", "There", "What", "Why", "How",
    "Run", "Lead", "Own", "Build", "Drive", "Deliver", "Design", "Develop", "Manage", "Write", "Work",
    "Set", "Kept", "Made", "Took", "Brought", "Moved", "Won", "Gave", "Taught", "Saw", "Began",
    "Additionally", "Furthermore", "Moreover", "Also", "Overall", "Together", "Finally", "Before",
    "After", "Since", "While", "When", "Then", "Beyond", "Both", "Each", "Several", "Many", "Such",
}


def _norm(text):
    return re.sub(r"\s+", " ", text or "").strip()


def _numbers(text):
    return {n.replace(",", "") for n in _NUMBER.findall(text or "")}


def _terms(text):
    """Names and tools in `text`. A verb opening a sentence ("Streamlined deploys...",
    "Leading...", or one in _STOP) is grammar, not a name; "Datadog dashboards..." is not."""
    out = set()
    for sentence in re.split(r"(?<=[.!?;:])\s+|\n|\s[-–—•]\s", text or ""):
        for m in _TERM.finditer(sentence):
            term = m.group(1).rstrip(".")
            opening = not sentence[:m.start()].strip(" \"'“‘(-–—•")
            if opening and re.fullmatch(r"[A-Z][a-z]+(?:ed|ing)", term):
                continue
            out.add(term)
    return out - _STOP


def _mentions(term, text):
    return re.search(rf"(?<![\w+#]){re.escape(term.lower())}(?![\w+#])", (text or "").lower()) is not None


def problems(text, source, job_skills=()):
    """What `text` claims that `source` doesn't say (empty list = fine)."""
    found = [f"the number {n}" for n in sorted(_numbers(text) - _numbers(source))]
    found += [f"“{t}”" for t in sorted(_terms(text)) if not _mentions(t, source)]
    for s in job_skills:
        if _mentions(s, text) and not _mentions(s, source) and f"“{s}”" not in found:
            found.append(f"“{s}”")
    return found


def resume_text(resume):
    """Every fact in the resume as one string (what a summary / cover note may draw on)."""
    parts = [resume.get("name", ""), resume.get("headline", ""), resume.get("location", ""),
             resume.get("summary", ""), ", ".join(resume.get("skills", []))]
    for r in resume.get("roles", []):
        parts += [r.get("title", ""), r.get("company", ""), r.get("location", ""),
                  r.get("start", ""), r.get("end", "")]
        parts += [b["text"] for b in r.get("bullets", [])]
    parts += resume.get("education", [])
    return "\n".join(p for p in parts if p)


def _sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", _norm(text)) if s]


def prompt(resume, job, requirements):
    slim = {"summary": resume.get("summary", ""), "skills": resume.get("skills", []),
            "roles": [{"id": r["id"], "title": r.get("title", ""), "company": r.get("company", ""),
                       "bullets": [{"id": b["id"], "text": b["text"]} for b in r.get("bullets", [])]}
                      for r in resume.get("roles", [])],
            "education": resume.get("education", [])}
    asks = ", ".join(requirements.get("required_skills", []) + requirements.get("preferred_skills", []))
    return PROMPT.format(title=job.get("title", ""), company=job.get("company") or "the employer",
                         asks=asks or "not stated", resume=json.dumps(slim, ensure_ascii=False))


def verify(raw, resume, job, requirements):
    """The model's answer -> a tailored resume that says nothing the resume doesn't, plus
    `log`: what was put back and why. `job` needs title and company."""
    job_skills = [s for s in requirements.get("required_skills", []) + requirements.get("preferred_skills", []) if s]
    everything = resume_text(resume)
    # The cover note may name the job it's for ("the SRE role at X").
    note_source = f"{everything}\n{job.get('title', '')}\n{job.get('company', '')}"
    log = []

    by_role = {r["id"]: r for r in resume.get("roles", [])}
    picks = {}
    for r in raw.get("roles") or []:
        if isinstance(r, dict) and r.get("id") in by_role and r["id"] not in picks:
            picks[r["id"]] = r.get("bullets") or []

    roles = []
    for role in resume.get("roles", []):
        originals = {b["id"]: b["text"] for b in role.get("bullets", [])}
        chosen = []
        for item in picks.get(role["id"], []):
            if len(chosen) == 5:
                break
            if not isinstance(item, dict) or item.get("id") not in originals:
                continue
            bid = item["id"]
            if any(c["id"] == bid for c in chosen):
                continue
            original, text = originals[bid], _norm(item.get("text"))
            entry = {"id": bid, "text": original, "original": original, "status": "kept"}
            if text and text != original:
                found = problems(text, original, job_skills)
                if len(text) > len(original) * 1.5 + 40:
                    found.append("a lot of new wording")
                if found:
                    entry.update(status="put_back", why="would have added " + ", ".join(found[:4]))
                    log.append(f"{role.get('title') or 'A role'}: kept your wording — the rewrite {entry['why']}.")
                else:
                    entry.update(text=text, status="reworded")
            chosen.append(entry)
        if not chosen:  # the model skipped this role: keep its first bullets as written
            chosen = [{"id": bid, "text": t, "original": t, "status": "kept"}
                      for bid, t in list(originals.items())[:2]]
        used = {c["id"] for c in chosen}
        roles.append({**{k: role.get(k, "") for k in ("id", "title", "company", "location", "start", "end")},
                      "bullets": chosen, "left_out": [t for bid, t in originals.items() if bid not in used]})

    summary, summary_status = _norm(raw.get("summary")), "tailored"
    found = problems(summary, everything, job_skills) if summary else None
    if found or not summary:
        if found:
            log.append("Summary: kept yours — the draft would have added " + ", ".join(found[:4]) + ".")
        summary, summary_status = resume.get("summary", ""), "original"

    own = {s.lower(): s for s in resume.get("skills", [])}
    skills = []
    for s in raw.get("skills") or []:
        key = s.strip().lower() if isinstance(s, str) else ""
        if key in own and own[key] not in skills:
            skills.append(own[key])
    skills += [s for s in resume.get("skills", []) if s not in skills]

    kept = [s for s in _sentences(raw.get("cover_note")) if not problems(s, note_source, job_skills)]
    left = len(_sentences(raw.get("cover_note"))) - len(kept)
    if left:
        log.append(f"Cover note: left out {left} sentence(s) that went beyond your resume.")

    return {
        "name": resume.get("name", ""), "headline": resume.get("headline", ""),
        "location": resume.get("location", ""), "links": resume.get("links", []),
        "education": resume.get("education", []), "contact": "",
        "summary": summary, "summary_original": resume.get("summary", ""), "summary_status": summary_status,
        "skills": skills, "roles": roles, "cover_note": " ".join(kept)[:1500], "log": log,
    }


def from_form(form, tailored):
    """The review form -> the tailored resume the user approved. What they type is theirs
    (they vouch for it, as on /profile); the structure (roles, dates) stays the resume's."""
    def lines(value, limit, width):
        return [_norm(x)[:width] for x in (value or "").splitlines() if x.strip()][:limit]

    roles = []
    for i, role in enumerate(tailored["roles"]):
        texts = lines(form.get(f"role-{i}-bullets"), 12, 400)
        roles.append({**role, "bullets": [{"id": f"{role['id']}e{j}", "text": t, "original": t, "status": "yours"}
                                          for j, t in enumerate(texts, 1)]})
    skills = []
    for s in re.split(r"[,\n]", form.get("skills", "")):
        s = s.strip()[:60]
        if s and s.lower() not in (x.lower() for x in skills):
            skills.append(s)
    return {**tailored, "summary": _norm(form.get("summary"))[:1200], "skills": skills[:60], "roles": roles,
            "cover_note": (form.get("cover_note") or "").strip()[:2000],
            "contact": _norm(form.get("contact"))[:200]}
