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
    -- posted_at_source normalised to UTC ISO by jobhub_poc/dates.py (NULL if unusable).
    -- Feeds only the "posted within" filter/sort, always COALESCEd with first_seen_at.
    posted_at         TEXT,
    first_seen_at     TEXT NOT NULL,
    last_seen_at      TEXT NOT NULL,
    raw_json          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_title         ON jobs(title);
CREATE INDEX IF NOT EXISTS idx_jobs_location      ON jobs(location);
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen_at ON jobs(first_seen_at);

-- Alerts v2 (2026-09-23). An alert is its owner's filters plus which of the owner's own
-- verified contacts it goes to -- no phone number of its own (contacts come from
-- auth-service at send time, see alerts/contacts.py). owner_auth_user_id is an opaque id
-- from auth-service's own user table (a different SQLite file), not a foreign key.
-- titles/locations/companies/keywords are JSON arrays of lower-case terms: OR within a
-- list, AND across lists (alerts/rules.py). db._migrate converts the pre-v2 shape.
CREATE TABLE IF NOT EXISTS alert_subscriptions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_auth_user_id  TEXT NOT NULL,
    titles              TEXT NOT NULL DEFAULT '[]',
    locations           TEXT NOT NULL DEFAULT '[]',
    companies           TEXT NOT NULL DEFAULT '[]',
    keywords            TEXT NOT NULL DEFAULT '[]',
    work_mode           TEXT CHECK (work_mode IN ('remote', 'onsite')),
    notify_email        INTEGER NOT NULL DEFAULT 0,
    notify_whatsapp     INTEGER NOT NULL DEFAULT 0,
    is_active           INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT NOT NULL,
    CHECK (notify_email + notify_whatsapp >= 1)
);
CREATE INDEX IF NOT EXISTS idx_alert_subscriptions_owner ON alert_subscriptions(owner_auth_user_id);

-- One row per (alert, job, channel) ever considered: SENT, FAILED, or SKIPPED (e.g. the
-- owner's contact for that channel isn't verified). The UNIQUE constraint is what makes a
-- re-run never re-send. Jobs from one digest share its message and sent_at.
CREATE TABLE IF NOT EXISTS alerts_sent (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id   INTEGER NOT NULL REFERENCES alert_subscriptions(id),
    job_id            INTEGER NOT NULL REFERENCES jobs(id),
    channel           TEXT NOT NULL CHECK (channel IN ('email', 'whatsapp')),
    notifier_backend  TEXT NOT NULL,
    message           TEXT NOT NULL,
    sent_at           TEXT NOT NULL,
    status            TEXT NOT NULL,
    UNIQUE(subscription_id, job_id, channel)
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

-- What signed-in users did with a job (opened details, clicked apply): history for the
-- future applications tracker and recommendations. Keyed by the job's dedupe_key plus a
-- snapshot, NOT a foreign key to jobs.id: purge deletes jobs, and this must outlive them.
CREATE TABLE IF NOT EXISTS job_interactions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_auth_user_id  TEXT NOT NULL,
    job_dedupe_key      TEXT NOT NULL,
    job_title           TEXT,
    job_company         TEXT,
    job_apply_url       TEXT,
    action              TEXT NOT NULL CHECK (action IN ('view_details', 'click_apply')),
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_job_interactions_owner ON job_interactions(owner_auth_user_id);

-- Small key/value state for the pipeline, e.g. "warehouse_watermark": the newest pi05
-- warehouse updated_at already applied here (loader/load_delta.py).
CREATE TABLE IF NOT EXISTS sync_state (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
