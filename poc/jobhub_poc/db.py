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
    _migrate_alerts_v2(conn)
    # Here, not in schema.sql: on an old database the column only exists after the ALTER.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_posted_or_seen ON jobs(COALESCE(posted_at, first_seen_at))"
    )


def _migrate_alerts_v2(conn: sqlite3.Connection) -> None:
    """Pre-v2 alert tables (a phone_number per alert, one title and location keyword,
    WhatsApp only, one alerts_sent row per (alert, job)) -> the v2 shape in schema.sql.
    Owned alerts keep their id and become titles=[kw], locations=[kw], WhatsApp to the
    owner's verified mobile; ownerless legacy alerts are dropped with their history."""
    columns = {r[1] for r in conn.execute("PRAGMA table_info(alert_subscriptions)")}
    if "phone_number" not in columns:
        return
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")  # has no effect inside a transaction
    try:
        conn.executescript("""
            BEGIN;
            ALTER TABLE alerts_sent RENAME TO alerts_sent_v1;
            ALTER TABLE alert_subscriptions RENAME TO alert_subscriptions_v1;
            DROP INDEX IF EXISTS idx_alert_subscriptions_owner;
        """ + _SCHEMA_PATH.read_text() + """
            INSERT INTO alert_subscriptions
                (id, owner_auth_user_id, titles, locations, notify_whatsapp, is_active, created_at)
            SELECT id, owner_auth_user_id,
                   CASE WHEN trim(coalesce(title_keyword, '')) = '' THEN '[]'
                        ELSE json_array(lower(trim(title_keyword))) END,
                   CASE WHEN trim(coalesce(location_keyword, '')) = '' THEN '[]'
                        ELSE json_array(lower(trim(location_keyword))) END,
                   1, is_active, created_at
            FROM alert_subscriptions_v1 WHERE owner_auth_user_id IS NOT NULL;
            INSERT INTO alerts_sent
                (id, subscription_id, job_id, channel, notifier_backend, message, sent_at, status)
            SELECT id, subscription_id, job_id, 'whatsapp', notifier_backend, message, sent_at, status
            FROM alerts_sent_v1 WHERE subscription_id IN (SELECT id FROM alert_subscriptions);
            DROP TABLE alerts_sent_v1;
            DROP TABLE alert_subscriptions_v1;
            COMMIT;
        """)
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
