"""What a signed-in user with a resume sees on /jobs by default: jobs for their roles in their
places ("Jobs for you"). Proposed from the checked resume by code -- the headline and the two
latest role titles, their title family, the resume's city and remote -- until the user saves
their own on /profile. Stored plain (job_preferences), like an alert's filters."""
import json
import re
from datetime import datetime, timezone

from jobhub_poc import places

# A role and the job titles that are the same kind of work (whole-word, case-insensitive).
TITLE_FAMILIES = [
    ("site reliability", "sre", "devops", "platform engineer", "infrastructure engineer", "cloud engineer"),
    ("devops", "site reliability", "sre", "platform engineer", "cloud engineer", "build and release"),
    ("data engineer", "etl developer", "big data", "data platform"),
    ("data scientist", "machine learning", "ml engineer", "ai engineer"),
    ("data analyst", "business analyst", "bi analyst", "analytics"),
    ("frontend", "front end", "ui developer", "react developer", "angular developer"),
    ("backend", "back end", "java developer", "python developer", "node developer", "api developer"),
    ("full stack", "fullstack", "mern", "mean stack"),
    ("qa", "quality assurance", "test engineer", "sdet", "automation tester"),
    ("product manager", "product owner"),
    ("project manager", "program manager", "delivery manager", "scrum master"),
]
_NOISE = re.compile(r"\b(senior|sr|junior|jr|lead|principal|staff|associate|trainee|intern|ii|iii|iv|i)\b\.?", re.I)


def _role(title):
    """'Senior SRE II' -> 'sre'."""
    return re.sub(r"\s+", " ", _NOISE.sub(" ", title or "")).strip(" ,-/").lower()


def propose(resume):
    """{"roles", "locations", "include_remote"} from a checked resume."""
    titles = [resume.get("headline") or ""] + [r.get("title") or "" for r in (resume.get("roles") or [])[:2]]
    roles = []
    for t in titles:
        role = _role(t)
        if role and role not in roles:
            roles.append(role)
    city = (resume.get("location") or "").split(",")[0].strip()
    wanted, _ = places.parse(city)
    return {"roles": roles[:5], "locations": wanted[:3], "include_remote": True}


def get(conn, user_id):
    row = conn.execute("SELECT roles_json, locations_json, include_remote FROM job_preferences "
                       "WHERE owner_auth_user_id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    return {"roles": json.loads(row[0]), "locations": json.loads(row[1]), "include_remote": bool(row[2])}


def save(conn, user_id, roles, locations, include_remote):
    clean = lambda items: [i for i in dict.fromkeys(" ".join(x.split())[:60] for x in items) if i][:8]  # noqa: E731
    conn.execute("""INSERT INTO job_preferences (owner_auth_user_id, roles_json, locations_json, include_remote, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (owner_auth_user_id) DO UPDATE SET roles_json = excluded.roles_json,
                      locations_json = excluded.locations_json, include_remote = excluded.include_remote,
                      updated_at = excluded.updated_at""",
                 (user_id, json.dumps(clean(roles)), json.dumps(clean(locations)), 1 if include_remote else 0,
                  datetime.now(timezone.utc).isoformat()))
    conn.commit()


def title_terms(roles):
    """Every title term that counts for these roles: each role and its title family."""
    terms = []
    for role in roles:
        r = role.lower().strip()
        if not r:
            continue
        terms.append(r)
        for family in TITLE_FAMILIES:
            if any(r == f or re.search(rf"(?<!\w){re.escape(f)}(?!\w)", r) for f in family):
                terms += family
    return list(dict.fromkeys(terms))


def location_text(prefs):
    """The location box text for these preferences: 'bengaluru, remote'."""
    return ", ".join(list(prefs["locations"]) + (["remote"] if prefs["include_remote"] else []))
