"""Several AI worker threads share one queue: every task is claimed exactly once."""
import sqlite3
import threading

from jobhub_poc import db
from jobhub_poc.ai import tasks


def test_parallel_workers_never_take_the_same_task(tmp_path):
    path = tmp_path / "jobhub.db"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    for n in range(30):
        tasks.enqueue(conn, "extract_job", ref=f"job-{n}", priority=1)
    tasks.enqueue(conn, "parse_resume", owner="u1", priority=10)
    conn.close()

    claimed, lock = [], threading.Lock()

    def drain():
        own = sqlite3.connect(path, timeout=30)
        own.row_factory = sqlite3.Row
        while (task := tasks.claim(own)) is not None:
            with lock:
                claimed.append(task["id"])
            tasks.finish(own, task["id"])
        own.close()

    threads = [threading.Thread(target=drain) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(claimed) == 31 and len(set(claimed)) == 31
    check = sqlite3.connect(path)
    assert check.execute("SELECT COUNT(*) FROM ai_tasks WHERE status = 'done' AND attempts = 1").fetchone()[0] == 31
