import json
import sqlite3

from jobhub_poc import db

OLD = """
CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, dedupe_key TEXT NOT NULL UNIQUE,
    external_job_id TEXT, source_site TEXT NOT NULL, search_term TEXT, title TEXT NOT NULL,
    company_name TEXT, location TEXT, description TEXT, employment_type TEXT,
    is_remote INTEGER NOT NULL DEFAULT 0, apply_url TEXT, posted_at_source TEXT, posted_at TEXT,
    first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, raw_json TEXT NOT NULL);
CREATE TABLE alert_subscriptions (id INTEGER PRIMARY KEY AUTOINCREMENT, phone_number TEXT NOT NULL,
    title_keyword TEXT, location_keyword TEXT, owner_auth_user_id TEXT,
    is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE INDEX idx_alert_subscriptions_owner ON alert_subscriptions(owner_auth_user_id);
CREATE TABLE alerts_sent (id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id INTEGER NOT NULL REFERENCES alert_subscriptions(id),
    job_id INTEGER NOT NULL REFERENCES jobs(id), notifier_backend TEXT NOT NULL,
    message TEXT NOT NULL, sent_at TEXT NOT NULL, status TEXT NOT NULL,
    UNIQUE(subscription_id, job_id));
INSERT INTO jobs (id, dedupe_key, source_site, title, first_seen_at, last_seen_at, raw_json)
    VALUES (1, 'k', 's', 'SRE', 'x', 'x', '{}');
INSERT INTO alert_subscriptions (id, phone_number, title_keyword, location_keyword, owner_auth_user_id, is_active, created_at)
    VALUES (5, '+15550000001', 'SRE', 'Bengaluru', 'u1', 1, 't'),
           (6, '+15550000002', NULL, NULL, NULL, 1, 't');          -- legacy: no owner
INSERT INTO alerts_sent (subscription_id, job_id, notifier_backend, message, sent_at, status)
    VALUES (5, 1, 'whatsapp', 'm', 's', 'SENT'), (6, 1, 'whatsapp', 'm', 's', 'SENT');
"""


def _old_db(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(OLD)
    conn.close()
    return path


def test_old_alert_tables_are_converted_keeping_owned_alerts(tmp_path):
    conn = db.get_connection(str(_old_db(tmp_path)))
    db.init_db(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(alert_subscriptions)")}
    assert "phone_number" not in cols and {"titles", "notify_whatsapp"} <= cols
    [sub] = [dict(r) for r in conn.execute("SELECT * FROM alert_subscriptions")]
    assert sub["id"] == 5 and sub["owner_auth_user_id"] == "u1"
    assert json.loads(sub["titles"]) == ["sre"] and json.loads(sub["locations"]) == ["bengaluru"]
    assert (sub["notify_whatsapp"], sub["notify_email"]) == (1, 0)
    [sent] = [dict(r) for r in conn.execute("SELECT * FROM alerts_sent")]
    assert (sent["subscription_id"], sent["channel"], sent["status"]) == (5, "whatsapp", "SENT")
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_migration_is_idempotent_and_new_rows_work(tmp_path):
    conn = db.get_connection(str(_old_db(tmp_path)))
    db.init_db(conn)
    db.init_db(conn)
    conn.execute("INSERT INTO alert_subscriptions (owner_auth_user_id, titles, notify_email, created_at) "
                 "VALUES ('u2', '[\"devops\"]', 1, 't')")
    conn.execute("INSERT INTO alerts_sent (subscription_id, job_id, channel, notifier_backend, message, sent_at, status) "
                 "VALUES (5, 1, 'email', 'live', 'm', 's', 'SENT')")  # same job, other channel: allowed
    conn.commit()
    assert conn.execute("SELECT count(*) FROM alerts_sent").fetchone()[0] == 2


def test_a_channel_is_required(conn):
    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO alert_subscriptions (owner_auth_user_id, created_at) VALUES ('u', 't')")
