import sqlite3

from jobhub_poc import db

# The v2 alert tables as they were live until 2026-09-24 (email and/or WhatsApp).
V2 = """
CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, dedupe_key TEXT NOT NULL UNIQUE,
    external_job_id TEXT, source_site TEXT NOT NULL, search_term TEXT, title TEXT NOT NULL,
    company_name TEXT, location TEXT, description TEXT, employment_type TEXT,
    is_remote INTEGER NOT NULL DEFAULT 0, apply_url TEXT, posted_at_source TEXT, posted_at TEXT,
    first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, raw_json TEXT NOT NULL);
CREATE TABLE alert_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, owner_auth_user_id TEXT NOT NULL,
    titles TEXT NOT NULL DEFAULT '[]', locations TEXT NOT NULL DEFAULT '[]',
    companies TEXT NOT NULL DEFAULT '[]', keywords TEXT NOT NULL DEFAULT '[]',
    work_mode TEXT CHECK (work_mode IN ('remote', 'onsite')),
    notify_email INTEGER NOT NULL DEFAULT 0, notify_whatsapp INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
    CHECK (notify_email + notify_whatsapp >= 1));
CREATE INDEX idx_alert_subscriptions_owner ON alert_subscriptions(owner_auth_user_id);
CREATE TABLE alerts_sent (id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id INTEGER NOT NULL REFERENCES alert_subscriptions(id),
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    channel TEXT NOT NULL CHECK (channel IN ('email', 'whatsapp')),
    notifier_backend TEXT NOT NULL, message TEXT NOT NULL, sent_at TEXT NOT NULL, status TEXT NOT NULL,
    UNIQUE(subscription_id, job_id, channel));
INSERT INTO jobs (id, dedupe_key, source_site, title, first_seen_at, last_seen_at, raw_json)
    VALUES (1, 'k', 's', 'SRE', 'x', 'x', '{}');
INSERT INTO alert_subscriptions (id, owner_auth_user_id, titles, locations, work_mode, notify_email, notify_whatsapp, is_active, created_at)
    VALUES (3, 'u1', '["sre","devops"]', '["remote"]', 'remote', 0, 1, 1, 't1'),
           (4, 'u1', '["qa"]', '[]', NULL, 1, 1, 0, 't2'),
           (7, 'u2', '["pm"]', '[]', NULL, 1, 0, 1, 't3');
INSERT INTO alerts_sent (id, subscription_id, job_id, channel, notifier_backend, message, sent_at, status)
    VALUES (10, 3, 1, 'whatsapp', 'live', 'm', 's', 'SENT'), (11, 4, 1, 'email', 'live', 'm', 's', 'FAILED');
"""


def _v2_db(tmp_path):
    path = tmp_path / "v2.db"
    conn = sqlite3.connect(path)
    conn.executescript(V2)
    conn.close()
    return path


def test_whatsapp_alerts_become_telegram_alerts_keeping_everything_else(tmp_path):
    conn = db.get_connection(str(_v2_db(tmp_path)))
    db.init_db(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(alert_subscriptions)")}
    assert "notify_whatsapp" not in cols and "notify_telegram" in cols
    subs = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM alert_subscriptions")}
    assert {i: (s["notify_email"], s["notify_telegram"], s["is_active"]) for i, s in subs.items()} == {
        3: (0, 1, 1), 4: (1, 1, 0), 7: (1, 0, 1)}
    assert (subs[3]["titles"], subs[3]["locations"], subs[3]["work_mode"], subs[3]["created_at"]) == (
        '["sre","devops"]', '["remote"]', "remote", "t1")
    sent = [tuple(r) for r in conn.execute("SELECT id, subscription_id, channel, status FROM alerts_sent ORDER BY id")]
    assert sent == [(10, 3, "whatsapp", "SENT"), (11, 4, "email", "FAILED")]
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    index = conn.execute("SELECT tbl_name FROM sqlite_master WHERE name = 'idx_alert_subscriptions_owner'").fetchone()
    assert index[0] == "alert_subscriptions"


def test_migration_is_idempotent_and_telegram_rows_work_after(tmp_path):
    conn = db.get_connection(str(_v2_db(tmp_path)))
    db.init_db(conn)
    db.init_db(conn)
    conn.execute("INSERT INTO alert_subscriptions (owner_auth_user_id, notify_telegram, created_at) VALUES ('u3', 1, 't')")
    conn.execute("INSERT INTO alerts_sent (subscription_id, job_id, channel, notifier_backend, message, sent_at, status) "
                 "VALUES (3, 1, 'telegram', 'live', 'm', 's', 'SENT')")
    try:
        conn.execute("INSERT INTO alert_subscriptions (owner_auth_user_id, created_at) VALUES ('u4', 't')")
        raise AssertionError("an alert with no channel must be refused")
    except sqlite3.IntegrityError:
        pass
