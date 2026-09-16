-- jobs: one row per distinct job posting we've ever seen.
-- Freshness/purge is keyed SOLELY on first_seen_at (set once, at load time) -- never on
-- posted_at_source, which real EverJobs data shows can be years stale or missing entirely.
CREATE TABLE IF NOT EXISTS jobs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    dedupe_key        TEXT NOT NULL UNIQUE,
    external_job_id   TEXT,
    source_site       TEXT NOT NULL,
    search_term       TEXT,
    title             TEXT NOT NULL,
    company_name      TEXT,
    location          TEXT,
    description       TEXT,
    employment_type   TEXT,
    is_remote         INTEGER NOT NULL DEFAULT 0,
    apply_url         TEXT,
    posted_at_source  TEXT,
    first_seen_at     TEXT NOT NULL,
    last_seen_at      TEXT NOT NULL,
    raw_json          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_title         ON jobs(title);
CREATE INDEX IF NOT EXISTS idx_jobs_location      ON jobs(location);
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen_at ON jobs(first_seen_at);

CREATE TABLE IF NOT EXISTS app_users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_subscriptions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_number        TEXT NOT NULL,
    title_keyword       TEXT,
    location_keyword    TEXT,
    created_by_user_id  INTEGER REFERENCES app_users(id),
    is_active           INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alert_subscriptions_active ON alert_subscriptions(is_active);

CREATE TABLE IF NOT EXISTS alerts_sent (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id   INTEGER NOT NULL REFERENCES alert_subscriptions(id),
    job_id            INTEGER NOT NULL REFERENCES jobs(id),
    notifier_backend  TEXT NOT NULL,
    message           TEXT NOT NULL,
    sent_at           TEXT NOT NULL,
    status            TEXT NOT NULL,
    UNIQUE(subscription_id, job_id)
);
