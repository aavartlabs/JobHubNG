"""How well a user's checked resume fits a job, and whether to apply. Deterministic, instant
and explainable -- no LLM here: it compares the structured resume (/profile) with the job's
cached requirements (job_requirements.py).

Score 0-100: required skills 45, preferred skills 15, experience 20, seniority 10,
location / work mode 10. Parts the posting says nothing about are left out and the rest
rescaled. A skill counts as matched if it's in the resume's skills or written in its
experience -- evidence the user already has, never assumed."""
import re
from datetime import date

from jobhub_poc.resume_review import parse_month

WEIGHTS = {"required": 45, "preferred": 15, "experience": 20, "seniority": 10, "location": 10}
VERDICTS = [  # (minimum score, key, label, advice)
    (75, "strong", "Strong match", "Apply — you meet most of what they ask."),
    (55, "good", "Good match", "Worth applying; lead with the matching skills."),
    (40, "stretch", "Stretch", "Apply if you're keen — address the gaps in your application."),
    (0, "weak", "Not a fit", "Probably not worth it unless you know something the posting doesn't say."),
]
# Same thing, different spellings. Both sides are normalised through this.
SYNONYMS = {
    "k8s": "kubernetes", "golang": "go", "js": "javascript", "ts": "typescript", "postgres": "postgresql",
    "gcp": "google cloud", "google cloud platform": "google cloud", "amazon web services": "aws",
    "ms excel": "excel", "microsoft excel": "excel", "ml": "machine learning", "ai": "artificial intelligence",
    "ci/cd": "ci cd", "cicd": "ci cd", "node": "node.js", "nodejs": "node.js", "react.js": "react", "reactjs": "react",
}
LEVELS = {"intern": 0, "junior": 1, "mid": 2, "senior": 3, "lead": 4, "manager": 4, "director": 5}
_TITLE_LEVELS = [(r"\b(intern|trainee|apprentice)\b", 0), (r"\b(junior|jr|associate|graduate)\b", 1),
                 (r"\b(director|vp|vice president|head|chief|cto|ceo)\b", 5),
                 (r"\b(lead|principal|staff|architect|manager)\b", 4), (r"\b(senior|sr)\b", 3)]


def norm_skill(skill):
    s = re.sub(r"\s+", " ", re.sub(r"[^\w+#./ -]", " ", (skill or "").lower())).strip(" .-")
    return SYNONYMS.get(s, s)


def _evidence(resume):
    skills = {norm_skill(s) for s in resume.get("skills") or []}
    parts = [resume.get("summary") or "", resume.get("headline") or ""]
    for role in resume.get("roles") or []:
        parts.append(role.get("title") or "")
        parts += [b.get("text") or "" for b in role.get("bullets") or []]
    blob = " " + re.sub(r"\s+", " ", " ".join(parts).lower()) + " "
    return skills, blob


def _has(skill, skills, blob):
    n = norm_skill(skill)
    if not n:
        return False
    if n in skills:
        return True
    variants = {n} | {k for k, v in SYNONYMS.items() if v == n}
    return any(re.search(rf"(?<![\w+#]){re.escape(v)}(?![\w+#])", blob) for v in variants)


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


def match(resume, requirements, job):
    """{score, verdict, label, advice, parts:{...}, matched/missing lists, notes[]}."""
    skills, blob = _evidence(resume)
    parts, notes = {}, []

    req = requirements.get("required_skills") or []
    pref = requirements.get("preferred_skills") or []
    matched_req = [s for s in req if _has(s, skills, blob)]
    missing_req = [s for s in req if s not in matched_req]
    matched_pref = [s for s in pref if _has(s, skills, blob)]
    if req:
        parts["required"] = len(matched_req) / len(req)
    if pref:
        parts["preferred"] = len(matched_pref) / len(pref)

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
    if job_level is not None and mine is not None:
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
                "matched_required": [], "missing_required": [], "matched_preferred": [], "notes": notes}
    _, key, label, advice = next(v for v in VERDICTS if score >= v[0])
    if req and len(missing_req) / len(req) > 0.6 and key in ("strong", "good"):
        key, label, advice = VERDICTS[2][1:]  # most must-haves missing: never better than a stretch
    if len(req) + len(pref) < 3:
        # Too little in the posting to be sure: say so, and don't call it "strong".
        notes.append("This posting lists few specific requirements, so this score is rough.")
        if key == "strong":
            key, label, advice = VERDICTS[1][1:]
    return {"score": score, "verdict": key, "label": label, "advice": advice, "parts": parts,
            "matched_required": matched_req, "missing_required": missing_req,
            "matched_preferred": matched_pref, "notes": notes}
