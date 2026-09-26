"""Runs queued AI tasks (ai/tasks.py) against the LLM (ai/llm.py), one at a time. While the LLM
host is unreachable it waits and checks again (backing off to a minute); queued work is
kept, never dropped. Container `jobhub-ai`: `python -m jobhub_poc.ai.worker`."""
import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

from jobhub_poc import (config, crypto, db, job_reading, job_requirements, match_evidence, resume_consent,
                        resume_parse, tailoring)
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
        model = "none"
    else:
        data, model = job_reading.read(conn, job["title"], text)  # Muse drafts, Jev decides
    job_requirements.store(conn, task["ref"], data, model)


def match(conn, task):
    """Jev's judgment of how the owner's resume shows what one job asks for (match_evidence)."""
    owner, key = task["owner_auth_user_id"], task["ref"]
    row = conn.execute("SELECT structured_enc, consent_at FROM resumes WHERE owner_auth_user_id = ?",
                       (owner,)).fetchone()
    job = conn.execute("SELECT title FROM jobs WHERE dedupe_key = ?", (key,)).fetchone()
    reqs = job_requirements.get_many(conn, [key]).get(key)
    if row is None or not row["structured_enc"] or job is None or reqs is None:
        return  # resume deleted, job purged, or not read yet (the page queues it again)
    _needs_consent(row)
    resume = crypto.decrypt_json(row["structured_enc"])
    data, model = match_evidence.judge(resume, reqs, job["title"])
    match_evidence.store(conn, owner, key, resume, reqs, data, model)


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


HANDLERS = {"parse_resume": parse_resume, "extract_job": extract_job, "tailor": tailor, "match": match}


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


def _loop(n):
    """One worker thread: its own database connection, the same queue as the others (claim
    is a single atomic UPDATE, so two threads never take the same task)."""
    conn = db.get_connection()
    wait = 5
    while True:
        if config.AI_PAUSED:  # paid AI switched off: queued work simply waits
            time.sleep(60)
            continue
        try:
            pending = tasks.pending_count(conn)
        except sqlite3.OperationalError as exc:  # "database is locked" while another writer commits
            log.warning("queue check failed (%s); retrying", exc)
            time.sleep(5)
            continue
        if pending == 0:
            time.sleep(3)
            continue
        if not llm.available():
            if n == 0:
                log.info("LLM unreachable; %d task(s) waiting", tasks.pending_count(conn))
            time.sleep(wait)
            wait = min(wait * 2, 60)
            continue
        try:
            while run_once(conn):
                wait = 5
        except sqlite3.OperationalError as exc:
            # Locked past the busy timeout, even while recording a failure: wait, then put back
            # anything this worker left 'running' (the task is retried, not lost).
            log.warning("database busy (%s); retrying", exc)
            time.sleep(5)
            try:
                tasks.requeue_stale(conn, older_than=timedelta(minutes=15) if config.AI_WORKERS > 1 else timedelta(0))
            except sqlite3.OperationalError:
                pass
        except llm.Unavailable as exc:
            # Busy (429) or unreachable: back off instead of retrying at once in a loop.
            log.info("AI service unavailable (%s); retrying in %d s", str(exc)[:120], wait)
            time.sleep(wait)
            wait = min(wait * 2, 60)


def main():
    """AI_WORKERS threads (hosted models answer in seconds but can take many requests at
    once: a job list queues ~25 job reads, which one thread would do one after another)."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    conn = db.get_connection()
    db.init_db(conn)
    # One worker process (the jobhub-ai container): anything still 'running' now was cut off
    # by its restart, so it goes straight back to the queue rather than after 15 minutes.
    for attempt in range(10):
        try:
            tasks.requeue_stale(conn, older_than=timedelta(0))
            break
        except sqlite3.OperationalError as exc:  # the pipeline is loading: wait for it
            log.warning("startup: database busy (%s); retrying", exc)
            time.sleep(10)
    conn.close()
    count = max(1, config.AI_WORKERS)
    log.info("AI worker: %d thread(s)", count)
    threads = [threading.Thread(target=_loop, args=(n,), daemon=True, name=f"ai-{n}") for n in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
