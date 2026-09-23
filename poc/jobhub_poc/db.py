import sqlite3
from pathlib import Path

from jobhub_poc import config

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection(path: str | None = None) -> sqlite3.Connection:
    db_path = path or config.SQLITE_PATH
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_PATH.read_text())
    _migrate(conn)
    conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    """In-place upgrades for databases created before a column existed. Idempotent."""
    columns = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    if "posted_at" not in columns:
        from jobhub_poc.dates import normalize_posted

        conn.execute("ALTER TABLE jobs ADD COLUMN posted_at TEXT")
        rows = conn.execute(
            "SELECT id, posted_at_source, first_seen_at FROM jobs WHERE posted_at_source IS NOT NULL"
        ).fetchall()
        conn.executemany(
            "UPDATE jobs SET posted_at = ? WHERE id = ?",
            [(normalize_posted(r[1], r[2]), r[0]) for r in rows],
        )
    # Here, not in schema.sql: on an old database the column only exists after the ALTER.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_posted_or_seen ON jobs(COALESCE(posted_at, first_seen_at))"
    )
