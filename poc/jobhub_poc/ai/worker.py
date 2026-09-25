"""Runs queued AI tasks (ai/tasks.py) against the LLM (ai/llm.py), one at a time. While the LLM
host is unreachable it waits and checks again (backing off to a minute); queued work is
kept, never dropped. Container `jobhub-ai`: `python -m jobhub_poc.ai.worker`."""
import logging
import time
from datetime import datetime, timezone

from jobhub_poc import crypto, db, job_requirements, resume_consent, resume_parse, tailoring
from jobhub_poc.webapp.job_text import plain_text
from jobhub_poc.ai import llm, tasks

log = logging.getLogger("jobhub.ai")


def _needs_consent(row):
    """Queued before the terms changed (resume_consent.py): no AI work until they agree again."""
    if not resume_consent.is_current(row["consent_at"]):
        raise resume_consent.ConsentNeeded("the owner hasn't agreed to the current resume terms")


def parse_resume(conn, task):
    row = conn.execute("SELECT text_enc, consent_at FROM resumes WHERE owner_auth_user_id = ?",
                       (task["owner_auth_user_id"],)).fetchone()
    if row is None:
        return  # deleted since it was queued
    _needs_consent(row)
    text = crypto.decrypt(row["text_enc"]).decode()
    raw = llm.generate(resume_parse.PROMPT + text, resume_parse.SCHEMA, timeout=600)
    structured = resume_parse.normalise(raw, text)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE resumes SET structured_enc = ?, parse_status = 'done', parse_error = NULL, updated_at = ? "
        "WHERE owner_auth_user_id = ?",
        (crypto.encrypt_json(structured), now, task["owner_auth_user_id"]))
    conn.commit()


def extract_job(conn, task):
    job = conn.execute("SELECT title, description FROM jobs WHERE dedupe_key = ?", (task["ref"],)).fetchone()
    if job is None:
        return  # purged since it was queued
    text = plain_text(job["description"])
    if len(text) < 100:
        data = {"required_skills": [], "preferred_skills": [], "min_years": None, "seniority": "unknown"}
    else:
        raw = llm.generate(job_requirements.PROMPT.format(title=job["title"], text=text),
                              job_requirements.SCHEMA, timeout=300)
        data = job_requirements.normalise(raw, f"{job['title']}\n{text}")
    job_requirements.store(conn, task["ref"], data, llm.model_name())


def tailor(conn, task):
    """The owner's checked resume, tailored for one job (ref = the job's dedupe_key), then
    checked fact by fact by tailoring.verify before anything is stored."""
    owner, key = task["owner_auth_user_id"], task["ref"]
    row = conn.execute("SELECT structured_enc, consent_at FROM resumes WHERE owner_auth_user_id = ?",
                       (owner,)).fetchone()
    job = conn.execute("SELECT title, company_name FROM jobs WHERE dedupe_key = ?", (key,)).fetchone()
    if row is None or not row["structured_enc"] or job is None:
        return  # resume deleted or job purged since it was queued
    _needs_consent(row)
    resume = crypto.decrypt_json(row["structured_enc"])
    reqs = job_requirements.get_many(conn, [key]).get(key)
    if reqs is None:
        extract_job(conn, task)
        reqs = job_requirements.get_many(conn, [key]).get(key) or {}
    info = {"title": job["title"], "company": job["company_name"] or ""}
    raw = llm.generate(tailoring.prompt(resume, info, reqs), tailoring.SCHEMA, timeout=600)
    tailored = tailoring.verify(raw, resume, info, reqs)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO tailored_resumes (owner_auth_user_id, job_dedupe_key, data_enc, status, model, created_at, updated_at)
           VALUES (?, ?, ?, 'ready', ?, ?, ?)
           ON CONFLICT (owner_auth_user_id, job_dedupe_key) DO UPDATE SET data_enc = excluded.data_enc,
             status = 'ready', model = excluded.model, created_at = excluded.created_at, updated_at = excluded.updated_at""",
        (owner, key, crypto.encrypt_json(tailored), llm.model_name(), now, now))
    conn.commit()


HANDLERS = {"parse_resume": parse_resume, "extract_job": extract_job, "tailor": tailor}


def run_once(conn):
    """True if a task was taken (done, failed or released), False if the queue is empty."""
    task = tasks.claim(conn)
    if task is None:
        return False
    handler = HANDLERS.get(task["kind"])
    try:
        if handler is None:
            raise RuntimeError(f"no handler for {task['kind']}")
        handler(conn, task)
        tasks.finish(conn, task["id"])
    except llm.Unavailable:
        tasks.release(conn, task["id"])
        raise
    except Exception as exc:  # noqa: BLE001 -- recorded on the task; the worker keeps going
        log.warning("task %s (%s) failed: %s", task["id"], task["kind"], exc)
        tasks.fail(conn, task["id"], exc, final=isinstance(exc, resume_consent.ConsentNeeded))
        if task["kind"] == "parse_resume":
            final = conn.execute("SELECT status FROM ai_tasks WHERE id = ?", (task["id"],)).fetchone()
            if final and final["status"] == "failed":
                message = ("Please agree to how we now use your resume (below) and we'll read it."
                           if isinstance(exc, resume_consent.ConsentNeeded)
                           else "We couldn't structure this resume automatically.")
                conn.execute("UPDATE resumes SET parse_status = 'failed', parse_error = ? WHERE owner_auth_user_id = ?",
                             (message, task["owner_auth_user_id"]))
                conn.commit()
    return True


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    conn = db.get_connection()
    db.init_db(conn)
    tasks.requeue_stale(conn)
    wait = 5
    while True:
        if tasks.pending_count(conn) == 0:
            time.sleep(3)
            continue
        if not llm.available():
            log.info("LLM unreachable; %d task(s) waiting", tasks.pending_count(conn))
            time.sleep(wait)
            wait = min(wait * 2, 60)
            continue
        wait = 5
        try:
            while run_once(conn):
                pass
        except llm.Unavailable:
            log.info("LLM went away mid-task; will retry")


if __name__ == "__main__":
    main()
