"""Runs queued AI tasks (ai/tasks.py) against the local LLM, one at a time. While the LLM
host is unreachable it waits and checks again (backing off to a minute); queued work is
kept, never dropped. Container `jobhub-ai`: `python -m jobhub_poc.ai.worker`."""
import logging
import time
from datetime import datetime, timezone

from jobhub_poc import crypto, db, resume_parse
from jobhub_poc.ai import ollama, tasks

log = logging.getLogger("jobhub.ai")


def parse_resume(conn, task):
    row = conn.execute("SELECT text_enc FROM resumes WHERE owner_auth_user_id = ?",
                       (task["owner_auth_user_id"],)).fetchone()
    if row is None:
        return  # deleted since it was queued
    text = crypto.decrypt(row["text_enc"]).decode()
    raw = ollama.generate(resume_parse.PROMPT + text, resume_parse.SCHEMA, timeout=600)
    structured = resume_parse.normalise(raw, text)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE resumes SET structured_enc = ?, parse_status = 'done', parse_error = NULL, updated_at = ? "
        "WHERE owner_auth_user_id = ?",
        (crypto.encrypt_json(structured), now, task["owner_auth_user_id"]))
    conn.commit()


HANDLERS = {"parse_resume": parse_resume}


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
    except ollama.OllamaUnavailable:
        tasks.release(conn, task["id"])
        raise
    except Exception as exc:  # noqa: BLE001 -- recorded on the task; the worker keeps going
        log.warning("task %s (%s) failed: %s", task["id"], task["kind"], exc)
        tasks.fail(conn, task["id"], exc)
        if task["kind"] == "parse_resume":
            final = conn.execute("SELECT status FROM ai_tasks WHERE id = ?", (task["id"],)).fetchone()
            if final and final["status"] == "failed":
                conn.execute("UPDATE resumes SET parse_status = 'failed', parse_error = ? WHERE owner_auth_user_id = ?",
                             ("We couldn't structure this resume automatically.", task["owner_auth_user_id"]))
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
        if not ollama.available():
            log.info("LLM unreachable; %d task(s) waiting", tasks.pending_count(conn))
            time.sleep(wait)
            wait = min(wait * 2, 60)
            continue
        wait = 5
        try:
            while run_once(conn):
                pass
        except ollama.OllamaUnavailable:
            log.info("LLM went away mid-task; will retry")


if __name__ == "__main__":
    main()
