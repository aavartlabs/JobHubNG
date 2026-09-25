"""How well a user's checked resume fits a job, and whether to apply. Deterministic and
explainable: the weights, caps and verdicts are code. What counts as "the resume shows this
skill" comes from Jev's judgment when there is one (match_evidence.py: evidence levels and
the bullet that shows it), else from literal matching of the structured resume (/profile)
against the job's cached requirements (job_requirements.py).

Score 0-100: required skills 45, preferred skills 15, experience 20, seniority 10,
location / work mode 10. Parts the posting says nothing about are left out and the rest
rescaled. A skill counts as matched if it's in the resume's skills or written in its
experience -- evidence the user already has, never assumed."""
import re
from datetime import date

from jobhub_poc import skills
from jobhub_poc.resume_review import parse_month

WEIGHTS = {"required": 45, "preferred": 15, "experience": 20, "seniority": 10, "location": 10}
# Credit for a skill by Jev's evidence level (0 none, 1 only listed, 2 used in a role, 3 used
# substantially with results; the score can fall between levels). "Matched" means used.
USED = 1.5


def _credit(level):
    return 1.0 if level >= 2.5 else 0.85 if level >= USED else 0.4 if level >= 0.5 else 0.0
VERDICTS = [  # (minimum score, key, label, advice)
    (75, "strong", "Strong match", "Apply — you meet most of what they ask."),
    (55, "good", "Good match", "Worth applying; lead with the matching skills."),
    (40, "stretch", "Stretch", "Apply if you're keen — address the gaps in your application."),
    (0, "weak", "Not a fit", "Probably not worth it unless you know something the posting doesn't say."),
]
LEVELS = {"intern": 0, "junior": 1, "mid": 2, "senior": 3, "lead": 4, "manager": 4, "director": 5}
_TITLE_LEVELS = [(r"\b(intern|trainee|apprentice)\b", 0), (r"\b(junior|jr|associate|graduate)\b", 1),
                 (r"\b(director|vp|vice president|head|chief|cto|ceo)\b", 5),
                 (r"\b(lead|principal|staff|architect|manager)\b", 4), (r"\b(senior|sr)\b", 3)]


def norm_skill(skill, index=None):
    """The skill's standard name (skills.py): "K8s" -> "kubernetes", "Dockers" -> "docker"."""
    return (index or skills.SEED_INDEX).canonical(skill)


def _evidence(resume, index):
    """The resume's skills and the 1-4 word phrases of its headline, summary, titles and
    bullets, by standard name -> the user's own wording (for "you wrote ...")."""
    listed = {}
    for s in resume.get("skills") or []:
        listed.setdefault(index.canonical(s), s)
    parts = [resume.get("summary") or "", resume.get("headline") or ""]
    for role in resume.get("roles") or []:
        parts.append(role.get("title") or "")
        parts += [b.get("text") or "" for b in role.get("bullets") or []]
    phrases = {}
    for part in parts:
        words = [w for w in re.split(r"[^\w+#./-]+", part) if w]
        for n in (4, 3, 2, 1):
            for i in range(len(words) - n + 1):
                phrase = " ".join(words[i:i + n])
                phrases.setdefault(index.canonical(phrase), phrase)
    return listed, phrases


def _has(skill, index, listed, phrases):
    """(matched, the user's wording or None)."""
    c = index.canonical(skill)
    if not c:
        return False, None
    if c in listed:
        return True, listed[c]
    if c in phrases:
        return True, phrases[c]
    for mine in listed.values():  # a typo in the user's skill list ("Kuberentes")
        if index.same(skill, mine):
            return True, mine
    return False, None


def years_of_experience(resume, today=None):
    """Total years across roles, overlapping periods counted once; None if no role has
    readable dates."""
    today = today or date.today()
    spans = []
    for role in resume.get("roles") or []:
        start, end = parse_month(role.get("start")), parse_month(role.get("end"))
        if not isinstance(start, tuple):
            continue
        # Months as [first, last+1): an end month counts in full ("Dec 2019" = through
        # December), a bare end year means through December ("2016 - 2019" = 4 years), and
        # a current role runs up to this month.
        if end in ("present", None):
            end_index = today.year * 12 + today.month
        elif isinstance(end, tuple):
            year_only = re.fullmatch(r"\s*(19|20)\d{2}\s*", role.get("end") or "") is not None
            end_index = end[0] * 12 + (12 if year_only else end[1]) + 1
        else:
            continue
        start_index = start[0] * 12 + start[1]
        if end_index <= start_index:
            continue
        spans.append((start_index, end_index))
    if not spans:
        return None
    spans.sort()
    months, cur_start, cur_end = 0, *spans[0]
    for s, e in spans[1:]:
        if s > cur_end:
            months += cur_end - cur_start
            cur_start, cur_end = s, e
        else:
            cur_end = max(cur_end, e)
    months += cur_end - cur_start
    return round(months / 12, 1)


def resume_level(resume, years):
    title = next((r.get("title") for r in resume.get("roles") or [] if r.get("title")), "") or resume.get("headline") or ""
    for pattern, level in _TITLE_LEVELS:
        if re.search(pattern, title.lower()):
            return level
    if years is None:
        return None
    return 1 if years < 2 else 2 if years < 5 else 3


def match(resume, requirements, job, evidence=None, index=None):
    """{score, verdict, label, advice, parts:{...}, matched/missing lists, notes[], lines{},
    wrote{}}. `evidence`: match_evidence's judgment for this resume and job, or None
    (literal). `index`: skills.Index (skills.current(conn)); the curated seed if None."""
    index = index or skills.SEED_INDEX
    listed, phrases = _evidence(resume, index)
    parts, notes = {}, []
    judged = (evidence or {}).get("skills") or {}
    wrote = {}

    def credit(skill):
        if skill in judged:
            return _credit(judged[skill].get("level") or 0.0)
        found, mine = _has(skill, index, listed, phrases)
        if found and mine and skills.normalise(mine) != skills.normalise(skill):
            wrote[skill] = mine
        return 1.0 if found else 0.0

    def used(skill):
        return credit(skill) >= 0.85

    req = requirements.get("required_skills") or []
    pref = requirements.get("preferred_skills") or []
    matched_req = [s for s in req if used(s)]
    missing_req = [s for s in req if s not in matched_req]
    matched_pref = [s for s in pref if used(s)]
    if req:
        parts["required"] = sum(credit(s) for s in req) / len(req)
    if pref:
        parts["preferred"] = sum(credit(s) for s in pref) / len(pref)
    listed_only = [s for s in req + pref if s in judged and 0.4 <= credit(s) < 0.85]
    if listed_only:
        notes.append("Listed on your resume but not shown in a role: " + ", ".join(listed_only[:5])
                     + ". Add a bullet that shows you using " + ("them." if len(listed_only) > 1 else "it."))
    lines = {s: judged[s]["line_text"] for s in matched_req + matched_pref if judged.get(s, {}).get("line_text")}

    years = years_of_experience(resume)
    need = requirements.get("min_years")
    if need:
        if years is None:
            parts["experience"] = 0.5
            notes.append(f"Asks for {need}+ years; add dates to your roles so we can compare.")
        else:
            short = need - years
            parts["experience"] = 1.0 if short <= 0 else 0.5 if short <= 1 else 0.0
            notes.append(f"Asks for {need}+ years; you have about {years:g}."
                         + (" A bit short." if 0 < short <= 1 else " Well short." if short > 1 else ""))
            if years >= need + 8 and requirements.get("seniority") in ("intern", "junior", "mid"):
                notes.append("You may be over-qualified for this level.")

    job_level = LEVELS.get(requirements.get("seniority") or "")
    mine = resume_level(resume, years)
    fit = (evidence or {}).get("seniority_fit")
    if job_level is not None and fit:
        parts["seniority"] = 1.0 if fit == "fit" else 0.5
        if fit == "below":
            notes.append("This role is more senior than your experience so far.")
        elif fit == "above":
            notes.append("This role is more junior than your experience.")
    elif job_level is not None and mine is not None:
        gap = job_level - mine
        parts["seniority"] = 1.0 if abs(gap) <= 0 else 0.6 if abs(gap) == 1 else 0.2
        if gap >= 2:
            notes.append("This role is more senior than your recent roles.")
        elif gap <= -2:
            notes.append("This role is more junior than your recent roles.")

    city = (resume.get("location") or "").split(",")[0].strip().lower()
    where = (job.get("location") or "").lower()
    if job.get("is_remote"):
        parts["location"] = 1.0
    elif not city:
        parts["location"] = 0.5
        notes.append("Add your city on your profile to judge location fit.")
    elif city and city in where or (city in ("bangalore", "bengaluru") and ("bangalore" in where or "bengaluru" in where)):
        parts["location"] = 1.0
    elif where:
        parts["location"] = 0.3
        notes.append(f"Based in {job.get('location')} — not where you are.")

    total_weight = sum(WEIGHTS[k] for k in parts)
    score = round(100 * sum(WEIGHTS[k] * v for k, v in parts.items()) / total_weight) if total_weight else None
    if score is None:
        return {"score": None, "verdict": "unknown", "label": "Not enough detail",
                "advice": "The posting doesn't say enough to compare.", "parts": parts,
                "matched_required": [], "missing_required": [], "matched_preferred": [], "notes": notes,
                "lines": {}, "wrote": {}, "judged": bool(judged)}
    _, key, label, advice = next(v for v in VERDICTS if score >= v[0])
    if req and len(missing_req) / len(req) > 0.6 and key in ("strong", "good"):
        key, label, advice = VERDICTS[2][1:]  # most must-haves missing: never better than a stretch
    same_field = (evidence or {}).get("same_field")
    if same_field is not None and same_field < 0.2:
        notes.append("Your experience is in a different kind of work from this role.")
        if key in ("strong", "good"):
            key, label, advice = VERDICTS[2][1:]
    if len(req) + len(pref) < 3:
        # Too little in the posting to be sure: say so, and don't call it "strong".
        notes.append("This posting lists few specific requirements, so this score is rough.")
        if key == "strong":
            key, label, advice = VERDICTS[1][1:]
    return {"score": score, "verdict": key, "label": label, "advice": advice, "parts": parts,
            "matched_required": matched_req, "missing_required": missing_req,
            "matched_preferred": matched_pref, "notes": notes, "lines": lines,
            "wrote": {k: v for k, v in wrote.items() if k in matched_req or k in matched_pref},
            "judged": bool(judged)}
