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
    conn.commit()
