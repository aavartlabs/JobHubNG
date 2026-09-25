"""How well a user's resume shows what a job asks for, judged by Jev (ai/judgments.py) and
used by matching.match as evidence in place of literal word matching: "K8s" counts for
Kubernetes, a skill only listed counts for less than one used in a role, and the match can
quote the user's own bullet as the reason.

Resume data goes to Jev without name, contact details or links, and only while the user's
consent is current (resume_consent.py). The answers are resume-derived, so they're stored
Fernet-encrypted (crypto.py) in match_evidence and valid only for the resume and the job
reading they were judged against. They're deleted with the resume, the account or the job.

state() tells the pages what to show: "ready" (evidence), "pending" (queued; show the
match as being worked out) or "literal" (no Jev: fall back to plain matching now)."""
import hashlib
import json
from datetime import datetime, timezone

from jobhub_poc import crypto, resume_consent
from jobhub_poc.ai import judgments, tasks, typesafe

MAX_SKILLS = 30
MAX_BULLETS = 200


def _rev(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def _bullets(resume):
    return [(b["id"], b.get("text") or "") for r in resume.get("roles") or [] for b in r.get("bullets") or []
            if b.get("id")][:MAX_BULLETS]


def state_for_jev(resume, reqs, job_title):
    """What Jev sees: the work history and skills, never the name, contact or links."""
    return {"resume": {"headline": resume.get("headline") or "", "summary": resume.get("summary") or "",
                       "skills": resume.get("skills") or [],
                       "roles": [{"title": r.get("title") or "", "company": r.get("company") or "",
                                  "start": r.get("start") or "", "end": r.get("end") or "",
                                  "bullets": [{"id": b["id"], "text": b.get("text") or ""}
                                              for b in r.get("bullets") or [] if b.get("id")]}
                                 for r in resume.get("roles") or []]},
            "job": {"title": job_title, "seniority": reqs.get("seniority") or "unknown",
                    "min_years": reqs.get("min_years"),
                    "required_skills": reqs.get("required_skills") or [],
                    "preferred_skills": reqs.get("preferred_skills") or []}}


def judge(resume, reqs, job_title):
    """(evidence, model). Raises typesafe.TypeSafeUnavailable when Jev can't answer now."""
    skills = ((reqs.get("required_skills") or []) + (reqs.get("preferred_skills") or []))[:MAX_SKILLS]
    bullets = _bullets(resume)
    ids = [bid for bid, _ in bullets]
    answers = typesafe.ask(state_for_jev(resume, reqs, job_title), judgments.match_questions(skills, ids))
    data = judgments.read_match_answers(answers, skills, ids)
    texts = dict(bullets)
    for v in data["skills"].values():
        v["line_text"] = texts.get(v["line"])
    return data, "jev"


def get(conn, user_id, job_key, resume, reqs):
    row = conn.execute("SELECT resume_rev, requirements_rev, data_enc FROM match_evidence "
                       "WHERE owner_auth_user_id = ? AND job_dedupe_key = ?", (user_id, job_key)).fetchone()
    if row is None or row[0] != _rev(resume) or row[1] != _rev(reqs):
        return None
    try:
        return crypto.decrypt_json(row[2])
    except crypto.CryptoUnavailable:
        return None


def store(conn, user_id, job_key, resume, reqs, data, model):
    conn.execute(
        """INSERT INTO match_evidence (owner_auth_user_id, job_dedupe_key, resume_rev, requirements_rev, data_enc, model, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (owner_auth_user_id, job_dedupe_key) DO UPDATE SET resume_rev = excluded.resume_rev,
             requirements_rev = excluded.requirements_rev, data_enc = excluded.data_enc, model = excluded.model,
             created_at = excluded.created_at""",
        (user_id, job_key, _rev(resume), _rev(reqs), crypto.encrypt_json(data), model,
         datetime.now(timezone.utc).isoformat()))
    conn.commit()


def state(conn, user_id, job_key, resume, reqs, priority):
    """("ready", evidence) | ("pending", None) | ("literal", None) -- see the module doc.
    Queues Jev's judgment when it's missing or out of date and Jev may be used."""
    evidence = get(conn, user_id, job_key, resume, reqs)
    if evidence is not None:
        return "ready", evidence
    consent = conn.execute("SELECT consent_at FROM resumes WHERE owner_auth_user_id = ?", (user_id,)).fetchone()
    if not typesafe.available() or consent is None or not resume_consent.is_current(consent[0]):
        return "literal", None
    failed = conn.execute("SELECT 1 FROM ai_tasks WHERE kind = 'match' AND owner_auth_user_id = ? AND ref = ? "
                          "AND status = 'failed' AND updated_at > ?", (user_id, job_key, _since_reading(conn, job_key))).fetchone()
    if failed:
        return "literal", None
    tasks.enqueue(conn, "match", owner=user_id, ref=job_key, priority=priority)
    return "pending", None


def _since_reading(conn, job_key):
    row = conn.execute("SELECT extracted_at FROM job_requirements WHERE job_dedupe_key = ?", (job_key,)).fetchone()
    return row[0] if row else ""

