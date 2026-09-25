"""A small work queue for AI jobs (ai_tasks table), run by worker.py. Queued work survives
the LLM host being off: it simply waits. Owner-scoped status for the UI via get()."""
from datetime import datetime, timedelta, timezone

MAX_ATTEMPTS = 3


def _now():
    return datetime.now(timezone.utc).isoformat()


def enqueue(conn, kind, owner=None, ref=None, priority=0, commit=True):
    """Task id; an identical task still queued or running is reused, not duplicated.
    commit=False for bulk queueing: the caller commits once (a commit per task locked the
    database for minutes on the Pi when every job was queued)."""
    row = conn.execute(
        "SELECT id FROM ai_tasks WHERE kind = ? AND owner_auth_user_id IS ? AND ref IS ? "
        "AND status IN ('queued', 'running')", (kind, owner, ref)).fetchone()
    if row:
        return row[0]
    now = _now()
    task_id = conn.execute(
        "INSERT INTO ai_tasks (kind, owner_auth_user_id, ref, priority, status, attempts, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 'queued', 0, ?, ?)", (kind, owner, ref, priority, now, now)).lastrowid
    if commit:
        conn.commit()
    return task_id


def claim(conn):
    """The next queued task (highest priority, oldest first), marked running; None if idle."""
    row = conn.execute(
        """UPDATE ai_tasks SET status = 'running', attempts = attempts + 1, updated_at = ?
           WHERE id = (SELECT id FROM ai_tasks WHERE status = 'queued' ORDER BY priority DESC, id LIMIT 1)
           RETURNING *""", (_now(),)).fetchone()
    conn.commit()
    return row


def finish(conn, task_id):
    conn.execute("UPDATE ai_tasks SET status = 'done', error = NULL, updated_at = ? WHERE id = ?", (_now(), task_id))
    conn.commit()


def fail(conn, task_id, error, final=False):
    """Back to the queue until MAX_ATTEMPTS (or at once, if `final`), then failed for good."""
    conn.execute(
        "UPDATE ai_tasks SET status = CASE WHEN attempts < ? THEN 'queued' ELSE 'failed' END, "
        "error = ?, updated_at = ? WHERE id = ?", (0 if final else MAX_ATTEMPTS, str(error)[:500], _now(), task_id))
    conn.commit()


def release(conn, task_id):
    """The LLM went away mid-task: requeue without spending an attempt."""
    conn.execute("UPDATE ai_tasks SET status = 'queued', attempts = MAX(attempts - 1, 0), updated_at = ? "
                 "WHERE id = ?", (_now(), task_id))
    conn.commit()


def requeue_stale(conn, older_than=timedelta(minutes=15)):
    """Tasks left 'running' by a worker that died."""
    cutoff = (datetime.now(timezone.utc) - older_than).isoformat()
    n = conn.execute("UPDATE ai_tasks SET status = 'queued' WHERE status = 'running' AND updated_at < ?",
                     (cutoff,)).rowcount
    conn.commit()
    return n


def get(conn, task_id, owner):
    return conn.execute("SELECT * FROM ai_tasks WHERE id = ? AND owner_auth_user_id = ?", (task_id, owner)).fetchone()


def pending_count(conn, owner=None):
    if owner is None:
        return conn.execute("SELECT count(*) FROM ai_tasks WHERE status IN ('queued', 'running')").fetchone()[0]
    return conn.execute("SELECT count(*) FROM ai_tasks WHERE status IN ('queued', 'running') "
                        "AND owner_auth_user_id = ?", (owner,)).fetchone()[0]
