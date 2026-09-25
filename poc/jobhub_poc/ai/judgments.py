"""Every question JobsHub asks Jev (ai/typesafe.py), and how its answers are read. Kept in one
place so wording and thresholds can be tuned and measured together (scripts/ai_bakeoff.py).

Jev picks among options we define; code decides what to do with its probabilities. An
answer below its confidence bar is treated as "can't tell", never guessed."""

MIN_CONFIDENCE = 0.5  # a categorical answer below this reads as unknown / unclear

# ---- Job reading (public job text) --------------------------------------------------------

SKILL_USE = {
    "required": "The posting says the candidate must have it: required, must-have, essential, or listed "
                "under requirements or qualifications.",
    "preferred": "The posting calls it a plus: nice to have, preferred, desirable, bonus.",
    "mentioned": "It appears in the posting, but not as something asked of the candidate (e.g. the "
                 "company's own product, a team they work with).",
    "absent": "The posting doesn't mention it at all.",
}
SENIORITY = {
    "intern": "Internship, trainee or working student.",
    "junior": "Entry level, graduate, junior or associate; about 0-2 years.",
    "mid": "Mid level; about 2-5 years, no lead duties.",
    "senior": "Senior; about 5+ years or 'senior' in the title.",
    "lead": "Lead, principal, staff or architect: leads the work of others without managing them.",
    "manager": "Manages people or a team.",
    "director": "Director, head of, VP or C-level.",
    "unknown": "The posting doesn't make the level clear.",
}
WORK_MODE = {"remote": "Fully remote.", "hybrid": "Some days in an office, some remote.",
             "onsite": "Works from the employer's site.", "unclear": "The posting doesn't say."}
EMPLOYMENT = {"full_time": "Permanent or full-time.", "part_time": "Part-time.",
              "contract": "Contract, freelance or fixed-term.", "internship": "Internship.",
              "temporary": "Temporary or seasonal.", "unclear": "The posting doesn't say."}
ROLE_FAMILY = {"engineering": "Software, hardware, infrastructure or other engineering.",
               "data": "Data engineering, analytics, data science or machine learning.",
               "design": "Product, UX, UI or graphic design.", "product": "Product or program management.",
               "sales": "Sales, business development or account management.",
               "marketing": "Marketing, content, communications or growth.",
               "operations": "Operations, supply chain, logistics, procurement or administration.",
               "finance": "Finance, accounting, audit, tax or legal.", "hr": "People, HR or recruiting.",
               "support": "Customer support, service or success.", "other": "Anything else."}


def job_questions(candidates, year_options):
    """Questions for one posting: how it treats each candidate skill, and the role's shape.
    `year_options`: whole numbers of years the posting states (the answer picks one)."""
    q = {f"skill_{i}": {"type": "choice", "instructions": f"How does this job posting treat “{s}”?",
                        "criteria": SKILL_USE}
         for i, s in enumerate(candidates)}
    q["seniority"] = {"type": "choice", "instructions": "What level is this role?", "criteria": SENIORITY}
    q["work_mode"] = {"type": "choice", "instructions": "Where is the work done?", "criteria": WORK_MODE}
    q["employment"] = {"type": "choice", "instructions": "What kind of employment is it?", "criteria": EMPLOYMENT}
    q["role_family"] = {"type": "choice", "instructions": "What kind of role is this?", "criteria": ROLE_FAMILY}
    q["min_years"] = {"type": "choice",
                      "instructions": "What is the minimum years of experience the posting asks for?",
                      "criteria": {**{f"y{n}": f"{n} years" for n in year_options},
                                   "not_stated": "It doesn't ask for a number of years."}}
    return q


def _pick(answer, allowed, default):
    choice = answer.get("choice")
    if choice in allowed and (answer.get("confidence") or 0) >= MIN_CONFIDENCE:
        return choice
    return default


def read_job_answers(answers, candidates):
    """Jev's answers -> the job_requirements shape (plus the new fields). A skill counts only
    when Jev says required or preferred."""
    required, preferred = [], []
    for i, skill in enumerate(candidates):
        a = answers[f"skill_{i}"]
        use = a.get("choice")
        if (a.get("probabilities") or {}).get(use, 0) < MIN_CONFIDENCE:
            continue
        (required if use == "required" else preferred if use == "preferred" else []).append(skill)
    years = _pick(answers["min_years"], {c for c in answers["min_years"].get("probabilities", {})}, "not_stated")
    return {
        "required_skills": required[:25], "preferred_skills": preferred[:25],
        "min_years": int(years[1:]) if years.startswith("y") and years[1:].isdigit() else None,
        "seniority": _pick(answers["seniority"], SENIORITY, "unknown"),
        "work_mode": _pick(answers["work_mode"], WORK_MODE, "unclear"),
        "employment": _pick(answers["employment"], EMPLOYMENT, "unclear"),
        "role_family": _pick(answers["role_family"], ROLE_FAMILY, "other"),
    }


# ---- Matching (resume x job; resume data) -------------------------------------------------

EVIDENCE_LEVELS = [
    "No evidence of it anywhere in the resume.",
    "Only listed as a skill; no role or bullet shows it being used.",
    "Used in at least one role (a bullet or role title shows it).",
    "Used substantially and recently, with a concrete result or scale.",
]
SENIORITY_FIT = {"below": "The candidate's experience is clearly below this role's level.",
                 "fit": "The candidate's experience matches this role's level.",
                 "above": "The candidate is clearly more senior than this role."}


def match_questions(skills, bullet_ids):
    """For each skill the job asks for: how strongly the resume shows it, and the one line
    that shows it best (by bullet id, so the answer points at the user's own words)."""
    q = {}
    for i, skill in enumerate(skills):
        q[f"evidence_{i}"] = {"type": "score", "criteria": EVIDENCE_LEVELS,
                              "instructions": f"How strongly does the resume show “{skill}”? Related names "
                                              "count (e.g. K8s for Kubernetes); related but different skills don't."}
        if bullet_ids:
            q[f"line_{i}"] = {"type": "choice",
                              "instructions": f"Which bullet in `resume.roles` (by its id) best shows “{skill}”?",
                              "criteria": {**{b: None for b in bullet_ids}, "none": "No bullet shows it."}}
    q["seniority_fit"] = {"type": "choice", "criteria": SENIORITY_FIT,
                          "instructions": "Compare the candidate's roles and years with `job.seniority` and the job title."}
    q["same_field"] = {"type": "noul",
                       "instructions": "Is the candidate's experience in the same kind of work as this job?"}
    return q


def read_match_answers(answers, skills, bullet_ids):
    """{"skills": {skill: {"level": 0..3, "line": bullet id | None}}, "seniority_fit", "same_field"}."""
    out = {}
    for i, skill in enumerate(skills):
        level = answers[f"evidence_{i}"].get("score")
        line = answers.get(f"line_{i}", {}).get("choice")
        conf = answers.get(f"line_{i}", {}).get("confidence") or 0
        out[skill] = {"level": float(level) if isinstance(level, (int, float)) else 0.0,
                      "line": line if line in bullet_ids and conf >= MIN_CONFIDENCE else None}
    return {"skills": out,
            "seniority_fit": _pick(answers["seniority_fit"], SENIORITY_FIT, None),
            "same_field": answers["same_field"].get("noul")}
