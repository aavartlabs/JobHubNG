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

-- owner_auth_user_id is an opaque id from poc/auth-service/'s own Better Auth user table
-- (a different SQLite file/service entirely) -- deliberately TEXT with no REFERENCES,
-- not a foreign key into anything in this database.
CREATE TABLE IF NOT EXISTS alert_subscriptions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_number        TEXT NOT NULL,
    title_keyword       TEXT,
    location_keyword    TEXT,
    owner_auth_user_id  TEXT,
    is_active           INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alert_subscriptions_active ON alert_subscriptions(is_active);
CREATE INDEX IF NOT EXISTS idx_alert_subscriptions_owner ON alert_subscriptions(owner_auth_user_id);

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

-- Admin console login (webapp/admin.py). Not end users -- those live in auth-service's
-- own auth.db. Set or rotate a password with scripts/set_admin_password.py.
CREATE TABLE IF NOT EXISTS app_users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    created_at     TEXT NOT NULL
);

-- Admin login brute-force counters, one row per "ip:<addr>" or "user:<name>" key.
-- locked_until is an ISO-8601 UTC timestamp; lock_count drives the doubling backoff.
CREATE TABLE IF NOT EXISTS admin_login_attempts (
    key           TEXT PRIMARY KEY,
    failures      INTEGER NOT NULL DEFAULT 0,
    lock_count    INTEGER NOT NULL DEFAULT 0,
    locked_until  TEXT,
    updated_at    TEXT NOT NULL
);
