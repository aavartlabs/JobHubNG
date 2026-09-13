
-- ============================================================
-- V1__foundation.sql
-- ============================================================
CREATE TABLE tenants (
  id BIGSERIAL PRIMARY KEY,
  tenant_key VARCHAR(80) NOT NULL UNIQUE,
  name VARCHAR(200) NOT NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
  id BIGSERIAL PRIMARY KEY,
  tenant_id BIGINT NULL REFERENCES tenants(id),
  email VARCHAR(320) NOT NULL UNIQUE,
  display_name VARCHAR(200) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE roles (
  id BIGSERIAL PRIMARY KEY,
  role_key VARCHAR(80) NOT NULL UNIQUE,
  display_name VARCHAR(120) NOT NULL
);

CREATE TABLE permissions (
  id BIGSERIAL PRIMARY KEY,
  permission_key VARCHAR(120) NOT NULL UNIQUE,
  description VARCHAR(250) NOT NULL
);

CREATE TABLE user_roles (
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_id BIGINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  PRIMARY KEY(user_id, role_id)
);

CREATE TABLE role_permissions (
  role_id BIGINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  permission_id BIGINT NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
  PRIMARY KEY(role_id, permission_id)
);

CREATE TABLE audit_events (
  id BIGSERIAL PRIMARY KEY,
  event_type VARCHAR(120) NOT NULL,
  actor_type VARCHAR(40) NOT NULL,
  actor_id BIGINT NULL,
  tenant_id BIGINT NULL REFERENCES tenants(id),
  correlation_id VARCHAR(120) NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_actor ON audit_events(actor_id, created_at DESC);
CREATE INDEX idx_audit_tenant ON audit_events(tenant_id, created_at DESC);

CREATE TABLE outbox_events (
  id UUID PRIMARY KEY,
  event_type VARCHAR(120) NOT NULL,
  aggregate_type VARCHAR(80) NOT NULL,
  aggregate_id VARCHAR(120) NOT NULL,
  tenant_id BIGINT NULL REFERENCES tenants(id),
  correlation_id VARCHAR(120) NOT NULL,
  payload JSONB NOT NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TIMESTAMPTZ NULL,
  published_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_outbox_pending ON outbox_events(status, next_attempt_at, created_at);

-- ============================================================
-- V2__seed_rbac.sql
-- ============================================================
INSERT INTO tenants(tenant_key,name) VALUES ('JOBHUB_PLATFORM','JobHub Platform') ON CONFLICT DO NOTHING;

INSERT INTO roles(role_key,display_name) VALUES
 ('JOB_SEEKER','Job Seeker'),
 ('STUDENT','Student / Fresher'),
 ('PROFESSIONAL','Working Professional'),
 ('RECRUITER','Recruiter / Hiring Manager'),
 ('EMPLOYER','Company / Employer'),
 ('ADMIN','Admin / Platform Ops')
ON CONFLICT DO NOTHING;

INSERT INTO permissions(permission_key,description) VALUES
 ('PLATFORM_READ','Read platform shell'),
 ('PROFILE_READ','Read own profile'),
 ('PROFILE_WRITE','Update own profile'),
 ('ADMIN_DATAFLOW_READ','Read platform data-flow diagnostics'),
 ('USER_READ','Read users'),
 ('AUDIT_READ','Read audit records')
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions(role_id,permission_id)
SELECT r.id,p.id FROM roles r CROSS JOIN permissions p
WHERE r.role_key IN ('JOB_SEEKER','STUDENT','PROFESSIONAL','RECRUITER','EMPLOYER')
  AND p.permission_key IN ('PLATFORM_READ','PROFILE_READ','PROFILE_WRITE')
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions(role_id,permission_id)
SELECT r.id,p.id FROM roles r CROSS JOIN permissions p
WHERE r.role_key='ADMIN'
ON CONFLICT DO NOTHING;

-- ============================================================
-- V3__create_jobhub_schemas_and_move_foundation.sql
-- ============================================================
-- JobHub schema namespaces and migration of Phase 0/1 foundation tables.
CREATE SCHEMA IF NOT EXISTS jobhub;
CREATE SCHEMA IF NOT EXISTS jobhub_user;
CREATE SCHEMA IF NOT EXISTS jobhub_taxonomy;
CREATE SCHEMA IF NOT EXISTS jobhub_ai;
CREATE SCHEMA IF NOT EXISTS jobhub_notification;
CREATE SCHEMA IF NOT EXISTS jobhub_analytics;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

ALTER TABLE IF EXISTS public.tenants SET SCHEMA jobhub_user;
ALTER TABLE IF EXISTS public.users SET SCHEMA jobhub_user;
ALTER TABLE IF EXISTS public.roles SET SCHEMA jobhub_user;
ALTER TABLE IF EXISTS public.permissions SET SCHEMA jobhub_user;
ALTER TABLE IF EXISTS public.user_roles SET SCHEMA jobhub_user;
ALTER TABLE IF EXISTS public.role_permissions SET SCHEMA jobhub_user;
ALTER TABLE IF EXISTS public.audit_events SET SCHEMA jobhub;
ALTER TABLE IF EXISTS public.outbox_events SET SCHEMA jobhub;

ALTER TABLE jobhub_user.users
    ADD COLUMN IF NOT EXISTS external_subject VARCHAR(255),
    ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_external_subject
    ON jobhub_user.users(external_subject)
    WHERE external_subject IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_tenant_status
    ON jobhub_user.users(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_user_roles_role
    ON jobhub_user.user_roles(role_id, user_id);

-- ============================================================
-- V4__job_sources_and_ingestion.sql
-- ============================================================
CREATE TABLE jobhub.job_sources (
    id                  BIGSERIAL PRIMARY KEY,
    code                VARCHAR(80) NOT NULL UNIQUE,
    name                VARCHAR(200) NOT NULL,
    source_type         VARCHAR(40) NOT NULL,
    access_mode         VARCHAR(30) NOT NULL DEFAULT 'API',
    base_url            TEXT,
    connector_class     VARCHAR(255),
    config_json         JSONB NOT NULL DEFAULT '{}'::jsonb,
    status              VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    schedule_expression VARCHAR(120),
    last_success_at     TIMESTAMPTZ,
    last_failure_at     TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_job_sources_status CHECK (status IN ('ACTIVE','PAUSED','DISABLED','ERROR')),
    CONSTRAINT ck_job_sources_type CHECK (source_type IN ('API','RSS','SCRAPER','PARTNER_FEED','EMPLOYER','RECRUITER','OTHER'))
);

CREATE TABLE jobhub.ingestion_runs (
    id                  BIGSERIAL PRIMARY KEY,
    source_id           BIGINT NOT NULL REFERENCES jobhub.job_sources(id),
    run_key             VARCHAR(160) NOT NULL UNIQUE,
    started_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at         TIMESTAMPTZ,
    status               VARCHAR(30) NOT NULL DEFAULT 'RUNNING',
    records_seen        INTEGER NOT NULL DEFAULT 0,
    records_inserted    INTEGER NOT NULL DEFAULT 0,
    records_duplicated  INTEGER NOT NULL DEFAULT 0,
    records_failed      INTEGER NOT NULL DEFAULT 0,
    error_count         INTEGER NOT NULL DEFAULT 0,
    cursor_value        TEXT,
    error_summary       TEXT,
    metadata_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT ck_ingestion_runs_status CHECK (status IN ('RUNNING','SUCCEEDED','PARTIAL','FAILED','CANCELLED')),
    CONSTRAINT ck_ingestion_runs_counts CHECK (
        records_seen >= 0 AND records_inserted >= 0 AND records_duplicated >= 0
        AND records_failed >= 0 AND error_count >= 0
    )
);

CREATE TABLE jobhub.jobs_raw (
    id                  BIGSERIAL PRIMARY KEY,
    ingestion_run_id    BIGINT REFERENCES jobhub.ingestion_runs(id),
    source_id           BIGINT NOT NULL REFERENCES jobhub.job_sources(id),
    external_job_id     VARCHAR(500),
    source_url          TEXT,
    payload             JSONB NOT NULL,
    payload_hash        VARCHAR(128) NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_jobs_raw_payload UNIQUE (source_id, external_job_id, payload_hash)
);

CREATE TABLE jobhub.job_raw_versions (
    id                  BIGSERIAL PRIMARY KEY,
    job_raw_id          BIGINT NOT NULL REFERENCES jobhub.jobs_raw(id) ON DELETE CASCADE,
    version_no          INTEGER NOT NULL,
    payload             JSONB NOT NULL,
    payload_hash        VARCHAR(128) NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (job_raw_id, version_no),
    UNIQUE (job_raw_id, payload_hash)
);

CREATE INDEX idx_jobs_raw_source_fetched
    ON jobhub.jobs_raw(source_id, fetched_at DESC);
CREATE INDEX idx_jobs_raw_external
    ON jobhub.jobs_raw(source_id, external_job_id);
CREATE INDEX idx_jobs_raw_payload_gin
    ON jobhub.jobs_raw USING GIN(payload jsonb_path_ops);
CREATE INDEX idx_ingestion_runs_source_started
    ON jobhub.ingestion_runs(source_id, started_at DESC);

-- ============================================================
-- V5__companies_and_canonical_jobs.sql
-- ============================================================
CREATE TABLE jobhub.companies (
    id                  BIGSERIAL PRIMARY KEY,
    tenant_id           BIGINT REFERENCES jobhub_user.tenants(id),
    name                VARCHAR(300) NOT NULL,
    normalized_name     VARCHAR(300) NOT NULL,
    legal_name          VARCHAR(500),
    website_url         TEXT,
    logo_url             TEXT,
    description         TEXT,
    industry_label      VARCHAR(200),
    headquarters_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
    status              VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (normalized_name),
    CONSTRAINT ck_companies_status CHECK (status IN ('ACTIVE','INACTIVE','BLOCKED'))
);

CREATE TABLE jobhub.jobs (
    id                       BIGSERIAL PRIMARY KEY,
    tenant_id                BIGINT REFERENCES jobhub_user.tenants(id),
    canonical_title          VARCHAR(500) NOT NULL,
    normalized_title         VARCHAR(500) NOT NULL,
    normalized_description   TEXT NOT NULL,
    company_id               BIGINT REFERENCES jobhub.companies(id),
    country_code             VARCHAR(10),
    city                     VARCHAR(200),
    postal_code              VARCHAR(40),
    status                   VARCHAR(40) NOT NULL DEFAULT 'PROCESSING',
    visibility               VARCHAR(30) NOT NULL DEFAULT 'PUBLIC',
    posted_at                TIMESTAMPTZ,
    published_at             TIMESTAMPTZ,
    expires_at               TIMESTAMPTZ,
    canonical_hash           VARCHAR(128),
    source_last_seen_at      TIMESTAMPTZ,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    version                  BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT ck_jobs_status CHECK (status IN ('RECEIVED','PROCESSING','PENDING_REVIEW','APPROVED','PUBLISHED','EXPIRED','REJECTED','DUPLICATE','ARCHIVED')),
    CONSTRAINT ck_jobs_visibility CHECK (visibility IN ('PUBLIC','PRIVATE','UNLISTED')),
    CONSTRAINT ck_jobs_dates CHECK (expires_at IS NULL OR posted_at IS NULL OR expires_at >= posted_at)
);

CREATE TABLE jobhub.job_sources_mapping (
    job_id              BIGINT NOT NULL REFERENCES jobhub.jobs(id) ON DELETE CASCADE,
    source_id           BIGINT NOT NULL REFERENCES jobhub.job_sources(id),
    external_job_id     VARCHAR(500),
    source_url          TEXT,
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    active               BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (job_id, source_id),
    UNIQUE (source_id, external_job_id)
);

CREATE TABLE jobhub.job_duplicate_candidates (
    id                  BIGSERIAL PRIMARY KEY,
    job_id              BIGINT NOT NULL REFERENCES jobhub.jobs(id) ON DELETE CASCADE,
    candidate_job_id    BIGINT NOT NULL REFERENCES jobhub.jobs(id) ON DELETE CASCADE,
    match_score         NUMERIC(6,5) NOT NULL,
    match_method        VARCHAR(40) NOT NULL,
    decision             VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    evidence_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
    reviewed_by         BIGINT REFERENCES jobhub_user.users(id),
    reviewed_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_duplicate_pair CHECK (job_id <> candidate_job_id AND job_id < candidate_job_id),
    CONSTRAINT ck_duplicate_score CHECK (match_score >= 0 AND match_score <= 1),
    CONSTRAINT ck_duplicate_decision CHECK (decision IN ('PENDING','DUPLICATE','NOT_DUPLICATE','MERGE')),
    UNIQUE (job_id, candidate_job_id)
);

CREATE TABLE jobhub.job_status_history (
    id                  BIGSERIAL PRIMARY KEY,
    job_id              BIGINT NOT NULL REFERENCES jobhub.jobs(id) ON DELETE CASCADE,
    from_status         VARCHAR(40),
    to_status           VARCHAR(40) NOT NULL,
    reason              VARCHAR(500),
    actor_type          VARCHAR(40) NOT NULL,
    actor_id            BIGINT,
    correlation_id      VARCHAR(120),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_companies_name_trgm
    ON jobhub.companies USING GIN(normalized_name gin_trgm_ops);
CREATE INDEX idx_companies_tenant_status
    ON jobhub.companies(tenant_id, status);
CREATE INDEX idx_jobs_status_published
    ON jobhub.jobs(status, published_at DESC);
CREATE INDEX idx_jobs_company_status
    ON jobhub.jobs(company_id, status);
CREATE INDEX idx_jobs_location
    ON jobhub.jobs(country_code, city);
CREATE INDEX idx_jobs_title_trgm
    ON jobhub.jobs USING GIN(normalized_title gin_trgm_ops);
CREATE INDEX idx_job_source_mapping_source
    ON jobhub.job_sources_mapping(source_id, active, last_seen_at DESC);
CREATE INDEX idx_duplicate_candidates_pending
    ON jobhub.job_duplicate_candidates(decision, match_score DESC);

-- ============================================================
-- V6__taxonomy_and_skills.sql
-- ============================================================
CREATE TABLE jobhub_taxonomy.taxonomy_types (
    id                  BIGSERIAL PRIMARY KEY,
    code                VARCHAR(80) NOT NULL UNIQUE,
    name                VARCHAR(200) NOT NULL,
    description         TEXT,
    status              VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    version_no          INTEGER NOT NULL DEFAULT 1,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_taxonomy_type_status CHECK (status IN ('ACTIVE','INACTIVE'))
);

CREATE TABLE jobhub_taxonomy.taxonomy_values (
    id                  BIGSERIAL PRIMARY KEY,
    taxonomy_type_id    BIGINT NOT NULL REFERENCES jobhub_taxonomy.taxonomy_types(id) ON DELETE CASCADE,
    parent_id           BIGINT REFERENCES jobhub_taxonomy.taxonomy_values(id),
    code                VARCHAR(120) NOT NULL,
    label               VARCHAR(250) NOT NULL,
    description         TEXT,
    status              VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    sort_order          INTEGER NOT NULL DEFAULT 0,
    metadata_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (taxonomy_type_id, code),
    CONSTRAINT ck_taxonomy_value_status CHECK (status IN ('ACTIVE','INACTIVE'))
);

CREATE TABLE jobhub_taxonomy.taxonomy_aliases (
    id                  BIGSERIAL PRIMARY KEY,
    taxonomy_value_id   BIGINT NOT NULL REFERENCES jobhub_taxonomy.taxonomy_values(id) ON DELETE CASCADE,
    alias               VARCHAR(250) NOT NULL,
    normalized_alias    VARCHAR(250) NOT NULL,
    source              VARCHAR(100),
    confidence          NUMERIC(5,4),
    UNIQUE (taxonomy_value_id, normalized_alias),
    CONSTRAINT ck_taxonomy_alias_confidence CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);
CREATE UNIQUE INDEX uq_taxonomy_alias_normalized
    ON jobhub_taxonomy.taxonomy_aliases(normalized_alias);

CREATE TABLE jobhub_taxonomy.skills (
    id                  BIGSERIAL PRIMARY KEY,
    name                VARCHAR(250) NOT NULL,
    normalized_name     VARCHAR(250) NOT NULL UNIQUE,
    skill_type          VARCHAR(50) NOT NULL DEFAULT 'TECHNICAL',
    category_taxonomy_value_id BIGINT REFERENCES jobhub_taxonomy.taxonomy_values(id),
    status              VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    metadata_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_skills_type CHECK (skill_type IN ('TECHNICAL','SOFT','DOMAIN','LANGUAGE','TOOL','CERTIFICATION','OTHER')),
    CONSTRAINT ck_skills_status CHECK (status IN ('ACTIVE','INACTIVE'))
);

CREATE TABLE jobhub_taxonomy.skill_aliases (
    id                  BIGSERIAL PRIMARY KEY,
    skill_id            BIGINT NOT NULL REFERENCES jobhub_taxonomy.skills(id) ON DELETE CASCADE,
    alias               VARCHAR(250) NOT NULL,
    normalized_alias    VARCHAR(250) NOT NULL,
    source              VARCHAR(100),
    UNIQUE (skill_id, normalized_alias)
);
CREATE UNIQUE INDEX uq_skill_alias_normalized
    ON jobhub_taxonomy.skill_aliases(normalized_alias);

CREATE INDEX idx_taxonomy_values_type_parent
    ON jobhub_taxonomy.taxonomy_values(taxonomy_type_id, parent_id, sort_order);
CREATE INDEX idx_taxonomy_alias_trgm
    ON jobhub_taxonomy.taxonomy_aliases USING GIN(normalized_alias gin_trgm_ops);
CREATE INDEX idx_skills_name_trgm
    ON jobhub_taxonomy.skills USING GIN(normalized_name gin_trgm_ops);
CREATE INDEX idx_skill_alias_trgm
    ON jobhub_taxonomy.skill_aliases USING GIN(normalized_alias gin_trgm_ops);

-- ============================================================
-- V7__job_intelligence.sql
-- ============================================================
CREATE TABLE jobhub.job_metadata (
    job_id                  BIGINT PRIMARY KEY REFERENCES jobhub.jobs(id) ON DELETE CASCADE,
    industry_taxonomy_id   BIGINT REFERENCES jobhub_taxonomy.taxonomy_values(id),
    function_taxonomy_id   BIGINT REFERENCES jobhub_taxonomy.taxonomy_values(id),
    employment_type_id     BIGINT REFERENCES jobhub_taxonomy.taxonomy_values(id),
    work_mode_id           BIGINT REFERENCES jobhub_taxonomy.taxonomy_values(id),
    seniority_id           BIGINT REFERENCES jobhub_taxonomy.taxonomy_values(id),
    education_level_id     BIGINT REFERENCES jobhub_taxonomy.taxonomy_values(id),
    country_taxonomy_id    BIGINT REFERENCES jobhub_taxonomy.taxonomy_values(id),
    salary_min             NUMERIC(18,2),
    salary_max             NUMERIC(18,2),
    salary_currency        VARCHAR(10),
    salary_period          VARCHAR(20),
    experience_min_years   NUMERIC(5,2),
    experience_max_years   NUMERIC(5,2),
    visa_required          BOOLEAN,
    remote_percentage      NUMERIC(5,2),
    normalized_location    JSONB NOT NULL DEFAULT '{}'::jsonb,
    benefits_json          JSONB NOT NULL DEFAULT '[]'::jsonb,
    languages_json         JSONB NOT NULL DEFAULT '[]'::jsonb,
    certifications_json    JSONB NOT NULL DEFAULT '[]'::jsonb,
    ai_confidence          NUMERIC(5,4),
    taxonomy_version       VARCHAR(80),
    extraction_version     VARCHAR(80),
    evidence_json          JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_job_metadata_salary CHECK (salary_min IS NULL OR salary_max IS NULL OR salary_max >= salary_min),
    CONSTRAINT ck_job_metadata_exp CHECK (experience_min_years IS NULL OR experience_max_years IS NULL OR experience_max_years >= experience_min_years),
    CONSTRAINT ck_job_metadata_conf CHECK (ai_confidence IS NULL OR (ai_confidence >= 0 AND ai_confidence <= 1)),
    CONSTRAINT ck_job_metadata_remote CHECK (remote_percentage IS NULL OR (remote_percentage >= 0 AND remote_percentage <= 100))
);

CREATE TABLE jobhub.job_skills (
    job_id              BIGINT NOT NULL REFERENCES jobhub.jobs(id) ON DELETE CASCADE,
    skill_id            BIGINT NOT NULL REFERENCES jobhub_taxonomy.skills(id),
    importance          VARCHAR(30) NOT NULL DEFAULT 'REQUIRED',
    years_required      NUMERIC(5,2),
    confidence          NUMERIC(5,4),
    evidence             TEXT,
    source               VARCHAR(40) NOT NULL DEFAULT 'AI',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (job_id, skill_id),
    CONSTRAINT ck_job_skill_importance CHECK (importance IN ('REQUIRED','PREFERRED','NICE_TO_HAVE')),
    CONSTRAINT ck_job_skill_conf CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

CREATE TABLE jobhub.job_embeddings (
    job_id              BIGINT PRIMARY KEY REFERENCES jobhub.jobs(id) ON DELETE CASCADE,
    embedding           vector(1536) NOT NULL,
    model_name          VARCHAR(100) NOT NULL,
    model_version       VARCHAR(80),
    embedding_text_hash VARCHAR(128),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_job_metadata_industry
    ON jobhub.job_metadata(industry_taxonomy_id);
CREATE INDEX idx_job_metadata_work_mode
    ON jobhub.job_metadata(work_mode_id);
CREATE INDEX idx_job_skills_skill
    ON jobhub.job_skills(skill_id, importance);
-- ANN index intentionally omitted until production workload and vector dimension are qualified.
;

-- ============================================================
-- V8__candidate_identity_and_preferences.sql
-- ============================================================
CREATE TABLE jobhub_user.user_profiles (
    user_id              BIGINT PRIMARY KEY REFERENCES jobhub_user.users(id) ON DELETE CASCADE,
    headline             VARCHAR(500),
    current_role         VARCHAR(300),
    years_experience     NUMERIC(5,2),
    bio                  TEXT,
    location_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
    target_roles_json    JSONB NOT NULL DEFAULT '[]'::jsonb,
    preferences_json     JSONB NOT NULL DEFAULT '{}'::jsonb,
    profile_visibility   VARCHAR(30) NOT NULL DEFAULT 'PRIVATE',
    profile_status       VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
    completeness_score   NUMERIC(5,2) NOT NULL DEFAULT 0,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_profile_visibility CHECK (profile_visibility IN ('PRIVATE','RECRUITERS','PUBLIC')),
    CONSTRAINT ck_profile_status CHECK (profile_status IN ('DRAFT','ACTIVE','HIDDEN')),
    CONSTRAINT ck_profile_complete CHECK (completeness_score >= 0 AND completeness_score <= 100)
);

CREATE TABLE jobhub_user.user_skills (
    user_id              BIGINT NOT NULL REFERENCES jobhub_user.users(id) ON DELETE CASCADE,
    skill_id             BIGINT NOT NULL REFERENCES jobhub_taxonomy.skills(id),
    proficiency_level    VARCHAR(30),
    years_experience     NUMERIC(5,2),
    last_used_year       INTEGER,
    evidence_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
    confidence           NUMERIC(5,4),
    verified              BOOLEAN NOT NULL DEFAULT FALSE,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, skill_id),
    CONSTRAINT ck_user_skill_proficiency CHECK (proficiency_level IS NULL OR proficiency_level IN ('BEGINNER','INTERMEDIATE','ADVANCED','EXPERT')),
    CONSTRAINT ck_user_skill_conf CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

CREATE TABLE jobhub_user.candidate_preferences (
    user_id                    BIGINT PRIMARY KEY REFERENCES jobhub_user.users(id) ON DELETE CASCADE,
    preferred_locations_json   JSONB NOT NULL DEFAULT '[]'::jsonb,
    preferred_countries_json   JSONB NOT NULL DEFAULT '[]'::jsonb,
    preferred_industries_json  JSONB NOT NULL DEFAULT '[]'::jsonb,
    preferred_roles_json       JSONB NOT NULL DEFAULT '[]'::jsonb,
    preferred_work_modes_json  JSONB NOT NULL DEFAULT '[]'::jsonb,
    preferred_job_types_json   JSONB NOT NULL DEFAULT '[]'::jsonb,
    salary_min                 NUMERIC(18,2),
    salary_max                 NUMERIC(18,2),
    salary_currency            VARCHAR(10),
    notice_period_days         INTEGER,
    relocation_open            BOOLEAN NOT NULL DEFAULT FALSE,
    stealth_search             BOOLEAN NOT NULL DEFAULT FALSE,
    alerts_enabled             BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE jobhub_user.candidate_embeddings (
    user_id              BIGINT PRIMARY KEY REFERENCES jobhub_user.users(id) ON DELETE CASCADE,
    embedding             vector(1536) NOT NULL,
    model_name            VARCHAR(100) NOT NULL,
    model_version         VARCHAR(80),
    embedding_text_hash   VARCHAR(128),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_user_profiles_role
    ON jobhub_user.user_profiles(current_role);
CREATE INDEX idx_user_skills_skill
    ON jobhub_user.user_skills(skill_id, proficiency_level);
CREATE INDEX idx_user_preferences_relocation
    ON jobhub_user.candidate_preferences(relocation_open, alerts_enabled);

-- ============================================================
-- V9__resumes_and_generated_documents.sql
-- ============================================================
CREATE TABLE jobhub_user.resumes (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT NOT NULL REFERENCES jobhub_user.users(id) ON DELETE CASCADE,
    file_name           VARCHAR(500) NOT NULL,
    object_key          VARCHAR(1000) NOT NULL,
    storage_provider    VARCHAR(40) NOT NULL DEFAULT 'S3',
    content_type        VARCHAR(120),
    size_bytes          BIGINT,
    sha256_hash         VARCHAR(128) NOT NULL,
    status              VARCHAR(30) NOT NULL DEFAULT 'UPLOADED',
    is_primary          BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_resume_status CHECK (status IN ('UPLOADED','PROCESSING','READY','REVIEW_REQUIRED','FAILED','ARCHIVED'))
);

CREATE TABLE jobhub_user.resume_versions (
    id                  BIGSERIAL PRIMARY KEY,
    resume_id           BIGINT NOT NULL REFERENCES jobhub_user.resumes(id) ON DELETE CASCADE,
    version_no          INTEGER NOT NULL,
    parser_version      VARCHAR(80),
    extracted_json      JSONB NOT NULL DEFAULT '{}'::jsonb,
    plain_text          TEXT,
    extraction_confidence NUMERIC(5,4),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (resume_id, version_no),
    CONSTRAINT ck_resume_version_conf CHECK (extraction_confidence IS NULL OR (extraction_confidence >= 0 AND extraction_confidence <= 1))
);

CREATE TABLE jobhub_user.generated_documents (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT NOT NULL REFERENCES jobhub_user.users(id) ON DELETE CASCADE,
    job_id              BIGINT REFERENCES jobhub.jobs(id),
    document_type       VARCHAR(40) NOT NULL,
    source_resume_id    BIGINT REFERENCES jobhub_user.resumes(id),
    object_key          VARCHAR(1000),
    content_text        TEXT,
    generation_status   VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
    model_name          VARCHAR(100),
    prompt_version      VARCHAR(100),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_generated_doc_type CHECK (document_type IN ('CV_REWRITE','COVER_LETTER','INTERVIEW_PLAN','PROFILE_SUMMARY','OTHER')),
    CONSTRAINT ck_generated_doc_status CHECK (generation_status IN ('DRAFT','READY','APPROVED','ARCHIVED','FAILED'))
);

CREATE INDEX idx_resumes_user_status
    ON jobhub_user.resumes(user_id, status, created_at DESC);
CREATE UNIQUE INDEX uq_primary_resume_per_user
    ON jobhub_user.resumes(user_id)
    WHERE is_primary = TRUE AND status <> 'ARCHIVED';
CREATE INDEX idx_generated_docs_user_job
    ON jobhub_user.generated_documents(user_id, job_id, created_at DESC);

-- ============================================================
-- V10__matching_saved_jobs_applications.sql
-- ============================================================
CREATE TABLE jobhub.job_matches (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT NOT NULL REFERENCES jobhub_user.users(id) ON DELETE CASCADE,
    job_id              BIGINT NOT NULL REFERENCES jobhub.jobs(id) ON DELETE CASCADE,
    match_score         NUMERIC(6,2) NOT NULL,
    semantic_score      NUMERIC(6,2),
    skill_score         NUMERIC(6,2),
    experience_score    NUMERIC(6,2),
    location_score      NUMERIC(6,2),
    preference_score    NUMERIC(6,2),
    explanation_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    generated_by        VARCHAR(100) NOT NULL,
    ranking_version     VARCHAR(80),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, job_id),
    CONSTRAINT ck_match_score CHECK (match_score >= 0 AND match_score <= 100)
);

CREATE TABLE jobhub.skill_gaps (
    id                  BIGSERIAL PRIMARY KEY,
    user_id              BIGINT NOT NULL REFERENCES jobhub_user.users(id) ON DELETE CASCADE,
    job_id               BIGINT REFERENCES jobhub.jobs(id) ON DELETE CASCADE,
    skill_id             BIGINT NOT NULL REFERENCES jobhub_taxonomy.skills(id),
    gap_level            VARCHAR(30) NOT NULL,
    current_proficiency  VARCHAR(30),
    required_importance  VARCHAR(30),
    rationale             TEXT,
    generated_by          VARCHAR(100),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_skill_gap_level CHECK (gap_level IN ('LOW','MEDIUM','HIGH','MISSING'))
);

CREATE TABLE jobhub.saved_jobs (
    user_id             BIGINT NOT NULL REFERENCES jobhub_user.users(id) ON DELETE CASCADE,
    job_id              BIGINT NOT NULL REFERENCES jobhub.jobs(id) ON DELETE CASCADE,
    status              VARCHAR(30) NOT NULL DEFAULT 'SAVED',
    note                TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, job_id),
    CONSTRAINT ck_saved_jobs_status CHECK (status IN ('SAVED','ARCHIVED'))
);

CREATE TABLE jobhub.applications (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT NOT NULL REFERENCES jobhub_user.users(id) ON DELETE CASCADE,
    job_id              BIGINT NOT NULL REFERENCES jobhub.jobs(id),
    status              VARCHAR(40) NOT NULL DEFAULT 'DRAFT',
    application_url     TEXT,
    source              VARCHAR(40) NOT NULL DEFAULT 'JOBHUB',
    applied_at          TIMESTAMPTZ,
    withdrawn_at        TIMESTAMPTZ,
    last_updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, job_id),
    CONSTRAINT ck_application_status CHECK (status IN ('DRAFT','SUBMITTED','VIEWED','SHORTLISTED','INTERVIEW','OFFER','HIRED','REJECTED','WITHDRAWN'))
);

CREATE TABLE jobhub.application_events (
    id                  BIGSERIAL PRIMARY KEY,
    application_id      BIGINT NOT NULL REFERENCES jobhub.applications(id) ON DELETE CASCADE,
    from_status         VARCHAR(40),
    to_status           VARCHAR(40) NOT NULL,
    actor_type          VARCHAR(40) NOT NULL,
    actor_id            BIGINT,
    note                TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_job_matches_user_score
    ON jobhub.job_matches(user_id, match_score DESC);
CREATE INDEX idx_job_matches_job_score
    ON jobhub.job_matches(job_id, match_score DESC);
CREATE INDEX idx_skill_gaps_user_job
    ON jobhub.skill_gaps(user_id, job_id);
CREATE INDEX idx_saved_jobs_user_created
    ON jobhub.saved_jobs(user_id, created_at DESC);
CREATE INDEX idx_applications_user_status
    ON jobhub.applications(user_id, status, created_at DESC);
CREATE INDEX idx_applications_job_status
    ON jobhub.applications(job_id, status, created_at DESC);

-- ============================================================
-- V11__recruiter_employer_domain.sql
-- ============================================================
CREATE TABLE jobhub.company_members (
    id                  BIGSERIAL PRIMARY KEY,
    company_id          BIGINT NOT NULL REFERENCES jobhub.companies(id) ON DELETE CASCADE,
    user_id             BIGINT NOT NULL REFERENCES jobhub_user.users(id) ON DELETE CASCADE,
    company_role        VARCHAR(40) NOT NULL,
    status              VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    joined_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company_id, user_id),
    CONSTRAINT ck_company_member_role CHECK (company_role IN ('OWNER','ADMIN','RECRUITER','HIRING_MANAGER','VIEWER')),
    CONSTRAINT ck_company_member_status CHECK (status IN ('ACTIVE','INVITED','SUSPENDED','REMOVED'))
);

CREATE TABLE jobhub.job_requisitions (
    id                  BIGSERIAL PRIMARY KEY,
    company_id          BIGINT NOT NULL REFERENCES jobhub.companies(id),
    created_by           BIGINT NOT NULL REFERENCES jobhub_user.users(id),
    assigned_to          BIGINT REFERENCES jobhub_user.users(id),
    job_id               BIGINT REFERENCES jobhub.jobs(id),
    requisition_code     VARCHAR(100) NOT NULL,
    title                VARCHAR(500) NOT NULL,
    description          TEXT,
    headcount            INTEGER NOT NULL DEFAULT 1,
    status               VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
    target_start_date    DATE,
    metadata_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company_id, requisition_code),
    CONSTRAINT ck_requisition_status CHECK (status IN ('DRAFT','OPEN','ON_HOLD','CLOSED','CANCELLED')),
    CONSTRAINT ck_requisition_headcount CHECK (headcount > 0)
);

CREATE TABLE jobhub.candidate_shortlists (
    id                  BIGSERIAL PRIMARY KEY,
    company_id           BIGINT NOT NULL REFERENCES jobhub.companies(id),
    job_id               BIGINT REFERENCES jobhub.jobs(id),
    candidate_user_id    BIGINT NOT NULL REFERENCES jobhub_user.users(id),
    added_by             BIGINT NOT NULL REFERENCES jobhub_user.users(id),
    status               VARCHAR(30) NOT NULL DEFAULT 'SHORTLISTED',
    match_score          NUMERIC(6,2),
    notes                TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_shortlist_status CHECK (status IN ('SHORTLISTED','CONTACTED','INTERVIEWING','REJECTED','HIRED')),
    CONSTRAINT ck_shortlist_score CHECK (match_score IS NULL OR (match_score >= 0 AND match_score <= 100))
);

CREATE TABLE jobhub.interviews (
    id                  BIGSERIAL PRIMARY KEY,
    company_id           BIGINT NOT NULL REFERENCES jobhub.companies(id),
    job_id               BIGINT REFERENCES jobhub.jobs(id),
    candidate_user_id    BIGINT NOT NULL REFERENCES jobhub_user.users(id),
    application_id       BIGINT REFERENCES jobhub.applications(id),
    created_by           BIGINT NOT NULL REFERENCES jobhub_user.users(id),
    interviewer_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    interview_type       VARCHAR(30) NOT NULL DEFAULT 'VIDEO',
    status               VARCHAR(30) NOT NULL DEFAULT 'SCHEDULED',
    start_at             TIMESTAMPTZ NOT NULL,
    end_at               TIMESTAMPTZ NOT NULL,
    meeting_url          TEXT,
    feedback_json        JSONB,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_interview_type CHECK (interview_type IN ('VIDEO','PHONE','ONSITE','ASSESSMENT','OTHER')),
    CONSTRAINT ck_interview_status CHECK (status IN ('SCHEDULED','COMPLETED','CANCELLED','NO_SHOW','RESCHEDULED')),
    CONSTRAINT ck_interview_dates CHECK (end_at > start_at)
);

CREATE TABLE jobhub.billing_accounts (
    id                  BIGSERIAL PRIMARY KEY,
    company_id          BIGINT NOT NULL UNIQUE REFERENCES jobhub.companies(id) ON DELETE CASCADE,
    plan_code            VARCHAR(80) NOT NULL DEFAULT 'FREE',
    status               VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    provider_customer_id VARCHAR(255),
    provider_subscription_id VARCHAR(255),
    current_period_end   TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_billing_status CHECK (status IN ('TRIAL','ACTIVE','PAST_DUE','CANCELLED','SUSPENDED'))
);

CREATE INDEX idx_company_members_user_status
    ON jobhub.company_members(user_id, status);
CREATE INDEX idx_requisitions_company_status
    ON jobhub.job_requisitions(company_id, status, updated_at DESC);
CREATE INDEX idx_shortlists_company_job
    ON jobhub.candidate_shortlists(company_id, job_id, status);
CREATE INDEX idx_interviews_candidate_start
    ON jobhub.interviews(candidate_user_id, start_at DESC);

-- ============================================================
-- V12__learning_and_notifications.sql
-- ============================================================
CREATE TABLE jobhub_user.learning_recommendations (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT NOT NULL REFERENCES jobhub_user.users(id) ON DELETE CASCADE,
    skill_gap_id        BIGINT REFERENCES jobhub.skill_gaps(id) ON DELETE SET NULL,
    job_id              BIGINT REFERENCES jobhub.jobs(id) ON DELETE SET NULL,
    provider_name       VARCHAR(200),
    external_resource_id VARCHAR(300),
    title               VARCHAR(500) NOT NULL,
    resource_url        TEXT,
    resource_type       VARCHAR(40),
    difficulty           VARCHAR(30),
    estimated_minutes   INTEGER,
    relevance_score     NUMERIC(6,2),
    rationale             TEXT,
    status               VARCHAR(30) NOT NULL DEFAULT 'RECOMMENDED',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_learning_status CHECK (status IN ('RECOMMENDED','SAVED','IN_PROGRESS','COMPLETED','DISMISSED')),
    CONSTRAINT ck_learning_score CHECK (relevance_score IS NULL OR (relevance_score >= 0 AND relevance_score <= 100))
);

CREATE TABLE jobhub_notification.notification_subscriptions (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT NOT NULL REFERENCES jobhub_user.users(id) ON DELETE CASCADE,
    subscription_type   VARCHAR(40) NOT NULL,
    query_json          JSONB NOT NULL DEFAULT '{}'::jsonb,
    channels_json       JSONB NOT NULL DEFAULT '["IN_APP"]'::jsonb,
    frequency           VARCHAR(30) NOT NULL DEFAULT 'DAILY',
    active              BOOLEAN NOT NULL DEFAULT TRUE,
    last_evaluated_at   TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_subscription_type CHECK (subscription_type IN ('JOB_ALERT','MATCH_ALERT','MARKET_ALERT','APPLICATION_ALERT','LEARNING_ALERT')),
    CONSTRAINT ck_subscription_frequency CHECK (frequency IN ('INSTANT','DAILY','WEEKLY'))
);

CREATE TABLE jobhub_notification.notifications (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT NOT NULL REFERENCES jobhub_user.users(id) ON DELETE CASCADE,
    subscription_id     BIGINT REFERENCES jobhub_notification.notification_subscriptions(id) ON DELETE SET NULL,
    notification_type   VARCHAR(50) NOT NULL,
    channel              VARCHAR(30) NOT NULL,
    status               VARCHAR(30) NOT NULL DEFAULT 'QUEUED',
    title               VARCHAR(500),
    body                TEXT,
    payload              JSONB NOT NULL DEFAULT '{}'::jsonb,
    scheduled_at        TIMESTAMPTZ,
    sent_at             TIMESTAMPTZ,
    read_at             TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_notification_channel CHECK (channel IN ('IN_APP','EMAIL','PUSH','WHATSAPP')),
    CONSTRAINT ck_notification_status CHECK (status IN ('QUEUED','SENDING','SENT','DELIVERED','FAILED','READ','CANCELLED'))
);

CREATE TABLE jobhub_notification.notification_attempts (
    id                  BIGSERIAL PRIMARY KEY,
    notification_id     BIGINT NOT NULL REFERENCES jobhub_notification.notifications(id) ON DELETE CASCADE,
    provider             VARCHAR(100) NOT NULL,
    provider_message_id VARCHAR(255),
    attempt_no           INTEGER NOT NULL,
    status               VARCHAR(30) NOT NULL,
    response_json        JSONB,
    error_code           VARCHAR(100),
    error_message        TEXT,
    attempted_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (notification_id, attempt_no),
    CONSTRAINT ck_notification_attempt_status CHECK (status IN ('SUCCESS','FAILED','RETRYING'))
);

CREATE INDEX idx_learning_user_status
    ON jobhub_user.learning_recommendations(user_id, status, created_at DESC);
CREATE INDEX idx_notification_subscriptions_user_active
    ON jobhub_notification.notification_subscriptions(user_id, active);
CREATE INDEX idx_notifications_user_status
    ON jobhub_notification.notifications(user_id, status, created_at DESC);
CREATE INDEX idx_notification_attempts_notification
    ON jobhub_notification.notification_attempts(notification_id, attempt_no DESC);

-- ============================================================
-- V13__market_analytics.sql
-- ============================================================
CREATE TABLE jobhub_analytics.market_snapshots (
    id                  BIGSERIAL PRIMARY KEY,
    snapshot_date       DATE NOT NULL,
    country_code        VARCHAR(10),
    industry_taxonomy_id BIGINT REFERENCES jobhub_taxonomy.taxonomy_values(id),
    skill_id            BIGINT REFERENCES jobhub_taxonomy.skills(id),
    role_label          VARCHAR(300),
    jobs_count          BIGINT NOT NULL DEFAULT 0,
    unique_companies    BIGINT NOT NULL DEFAULT 0,
    median_salary       NUMERIC(18,2),
    salary_currency     VARCHAR(10),
    remote_jobs_count   BIGINT NOT NULL DEFAULT 0,
    source_count        INTEGER NOT NULL DEFAULT 0,
    metrics_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (snapshot_date, country_code, industry_taxonomy_id, skill_id, role_label)
);

CREATE TABLE jobhub_analytics.market_forecasts (
    id                  BIGSERIAL PRIMARY KEY,
    generated_for_date  DATE NOT NULL,
    horizon_days        INTEGER NOT NULL,
    country_code        VARCHAR(10),
    industry_taxonomy_id BIGINT REFERENCES jobhub_taxonomy.taxonomy_values(id),
    skill_id            BIGINT REFERENCES jobhub_taxonomy.skills(id),
    role_label          VARCHAR(300),
    metric_name         VARCHAR(100) NOT NULL,
    forecast_value      NUMERIC(18,6) NOT NULL,
    lower_bound         NUMERIC(18,6),
    upper_bound         NUMERIC(18,6),
    model_name          VARCHAR(150) NOT NULL,
    model_version       VARCHAR(80),
    confidence          NUMERIC(5,4),
    feature_window      VARCHAR(100),
    explanation_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_forecast_horizon CHECK (horizon_days > 0),
    CONSTRAINT ck_forecast_confidence CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    CONSTRAINT ck_forecast_interval CHECK (lower_bound IS NULL OR upper_bound IS NULL OR lower_bound <= upper_bound)
);

CREATE TABLE jobhub_analytics.analytics_jobs_daily (
    metric_date         DATE NOT NULL,
    metric_key          VARCHAR(120) NOT NULL,
    dimension_json      JSONB NOT NULL DEFAULT '{}'::jsonb,
    metric_value        NUMERIC(20,6) NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (metric_date, metric_key, dimension_json)
);

CREATE INDEX idx_market_snapshots_date
    ON jobhub_analytics.market_snapshots(snapshot_date DESC);
CREATE INDEX idx_market_snapshots_skill_date
    ON jobhub_analytics.market_snapshots(skill_id, snapshot_date DESC);
CREATE INDEX idx_market_forecasts_key_date
    ON jobhub_analytics.market_forecasts(metric_name, generated_for_date DESC);
CREATE INDEX idx_analytics_jobs_daily_metric
    ON jobhub_analytics.analytics_jobs_daily(metric_key, metric_date DESC);

-- ============================================================
-- V14__ai_governance_and_human_review.sql
-- ============================================================
CREATE TABLE jobhub_ai.agent_definitions (
    id                  BIGSERIAL PRIMARY KEY,
    agent_key            VARCHAR(120) NOT NULL UNIQUE,
    name                 VARCHAR(200) NOT NULL,
    purpose              TEXT NOT NULL,
    implementation_type VARCHAR(50) NOT NULL DEFAULT 'OPENAI_AGENTS_SDK',
    version_no           VARCHAR(50) NOT NULL,
    status               VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    configuration_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_agent_status CHECK (status IN ('ACTIVE','INACTIVE','DEPRECATED'))
);

CREATE TABLE jobhub_ai.prompt_versions (
    id                  BIGSERIAL PRIMARY KEY,
    agent_definition_id BIGINT NOT NULL REFERENCES jobhub_ai.agent_definitions(id) ON DELETE CASCADE,
    version_no          VARCHAR(50) NOT NULL,
    prompt_text         TEXT NOT NULL,
    prompt_hash         VARCHAR(128) NOT NULL,
    status               VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (agent_definition_id, version_no),
    CONSTRAINT ck_prompt_status CHECK (status IN ('DRAFT','ACTIVE','RETIRED'))
);

CREATE TABLE jobhub_ai.ai_processing_runs (
    id                  BIGSERIAL PRIMARY KEY,
    entity_type         VARCHAR(80) NOT NULL,
    entity_id           BIGINT NOT NULL,
    workflow_instance_id VARCHAR(120),
    agent_definition_id BIGINT REFERENCES jobhub_ai.agent_definitions(id),
    agent_name          VARCHAR(200) NOT NULL,
    agent_version       VARCHAR(50) NOT NULL,
    model_name          VARCHAR(150),
    prompt_version      VARCHAR(100),
    input_hash          VARCHAR(128),
    output_json         JSONB,
    confidence          NUMERIC(5,4),
    status              VARCHAR(30) NOT NULL,
    trace_id            VARCHAR(150),
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    error_code          VARCHAR(100),
    error_message       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_ai_run_conf CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    CONSTRAINT ck_ai_run_status CHECK (status IN ('RUNNING','SUCCESS','REVIEW','FAILED','CANCELLED'))
);

CREATE TABLE jobhub_ai.ai_tool_calls (
    id                  BIGSERIAL PRIMARY KEY,
    processing_run_id   BIGINT NOT NULL REFERENCES jobhub_ai.ai_processing_runs(id) ON DELETE CASCADE,
    tool_name           VARCHAR(200) NOT NULL,
    target_type         VARCHAR(80),
    target_id            VARCHAR(120),
    input_hash          VARCHAR(128),
    output_metadata     JSONB,
    status               VARCHAR(30) NOT NULL,
    latency_ms           BIGINT,
    error_code          VARCHAR(100),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_ai_tool_status CHECK (status IN ('SUCCESS','FAILED','DENIED','TIMEOUT'))
);

CREATE TABLE jobhub_ai.ai_evaluation_cases (
    id                  BIGSERIAL PRIMARY KEY,
    case_key            VARCHAR(160) NOT NULL UNIQUE,
    agent_key            VARCHAR(120) NOT NULL,
    scenario             TEXT NOT NULL,
    input_json           JSONB NOT NULL,
    expected_output_json JSONB,
    evaluation_rules_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    active              BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE jobhub_ai.ai_evaluation_runs (
    id                  BIGSERIAL PRIMARY KEY,
    evaluation_case_id  BIGINT NOT NULL REFERENCES jobhub_ai.ai_evaluation_cases(id) ON DELETE CASCADE,
    agent_version       VARCHAR(50) NOT NULL,
    model_name          VARCHAR(150),
    actual_output_json  JSONB,
    score               NUMERIC(6,4),
    passed              BOOLEAN,
    trace_id            VARCHAR(150),
    run_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_eval_score CHECK (score IS NULL OR (score >= 0 AND score <= 1))
);

CREATE TABLE jobhub_ai.agent_sessions (
    id                  UUID PRIMARY KEY,
    user_id             BIGINT REFERENCES jobhub_user.users(id) ON DELETE SET NULL,
    tenant_id           BIGINT REFERENCES jobhub_user.tenants(id) ON DELETE SET NULL,
    agent_key            VARCHAR(120) NOT NULL,
    session_status       VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    context_json         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_activity_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_agent_session_status CHECK (session_status IN ('ACTIVE','CLOSED','EXPIRED'))
);

CREATE TABLE jobhub_ai.human_review_tasks (
    id                  BIGSERIAL PRIMARY KEY,
    workflow_instance_id VARCHAR(120) NOT NULL,
    task_key            VARCHAR(120),
    entity_type         VARCHAR(80) NOT NULL,
    entity_id           BIGINT NOT NULL,
    reason              VARCHAR(500) NOT NULL,
    priority            VARCHAR(20) NOT NULL DEFAULT 'NORMAL',
    payload             JSONB NOT NULL DEFAULT '{}'::jsonb,
    assigned_to         BIGINT REFERENCES jobhub_user.users(id),
    status               VARCHAR(30) NOT NULL DEFAULT 'OPEN',
    decision            JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    assigned_at         TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    CONSTRAINT ck_review_priority CHECK (priority IN ('LOW','NORMAL','HIGH','CRITICAL')),
    CONSTRAINT ck_review_status CHECK (status IN ('OPEN','IN_PROGRESS','APPROVED','EDITED','REJECTED','CANCELLED'))
);

CREATE INDEX idx_ai_runs_entity
    ON jobhub_ai.ai_processing_runs(entity_type, entity_id, created_at DESC);
CREATE INDEX idx_ai_runs_trace
    ON jobhub_ai.ai_processing_runs(trace_id);
CREATE INDEX idx_ai_tool_calls_run
    ON jobhub_ai.ai_tool_calls(processing_run_id, created_at DESC);
CREATE INDEX idx_ai_eval_runs_case
    ON jobhub_ai.ai_evaluation_runs(evaluation_case_id, run_at DESC);
CREATE INDEX idx_agent_sessions_user_activity
    ON jobhub_ai.agent_sessions(user_id, last_activity_at DESC);
CREATE INDEX idx_human_review_open
    ON jobhub_ai.human_review_tasks(status, priority, created_at);
CREATE INDEX idx_human_review_entity
    ON jobhub_ai.human_review_tasks(entity_type, entity_id);

-- ============================================================
-- V15__audit_outbox_extensions_and_integrity.sql
-- ============================================================
ALTER TABLE jobhub.outbox_events
    ADD COLUMN IF NOT EXISTS available_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS locked_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS locked_by VARCHAR(120),
    ADD COLUMN IF NOT EXISTS last_error TEXT;

UPDATE jobhub.outbox_events
SET available_at = COALESCE(available_at, next_attempt_at, created_at)
WHERE available_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_outbox_claimable
    ON jobhub.outbox_events(status, available_at, created_at);
CREATE INDEX IF NOT EXISTS idx_outbox_aggregate
    ON jobhub.outbox_events(aggregate_type, aggregate_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_event_type
    ON jobhub.audit_events(event_type, created_at DESC);

CREATE OR REPLACE FUNCTION jobhub.touch_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'jobhub.job_sources',
        'jobhub.companies',
        'jobhub.jobs',
        'jobhub.job_metadata',
        'jobhub_taxonomy.taxonomy_types',
        'jobhub_taxonomy.taxonomy_values',
        'jobhub_taxonomy.skills',
        'jobhub_user.users',
        'jobhub_user.user_profiles',
        'jobhub_user.user_skills',
        'jobhub_user.candidate_preferences',
        'jobhub_user.resumes',
        'jobhub_user.generated_documents',
        'jobhub.job_matches',
        'jobhub.saved_jobs',
        'jobhub.job_requisitions',
        'jobhub.candidate_shortlists',
        'jobhub.interviews',
        'jobhub.billing_accounts',
        'jobhub_user.learning_recommendations',
        'jobhub_notification.notification_subscriptions',
        'jobhub_notification.notifications',
        'jobhub_ai.agent_definitions'
    ]
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_touch_updated_at ON %s', t);
        EXECUTE format('CREATE TRIGGER trg_touch_updated_at BEFORE UPDATE ON %s FOR EACH ROW EXECUTE FUNCTION jobhub.touch_updated_at()', t);
    END LOOP;
END$$;

ALTER TABLE jobhub.jobs
    ADD CONSTRAINT uq_jobs_canonical_hash UNIQUE (canonical_hash);
CREATE INDEX IF NOT EXISTS idx_jobs_expiry
    ON jobhub.jobs(expires_at)
    WHERE status = 'PUBLISHED';

ALTER TABLE jobhub.jobs_raw
    ADD CONSTRAINT ck_jobs_raw_payload_nonempty CHECK (jsonb_typeof(payload) IS NOT NULL);

-- ============================================================
-- V16__seed_taxonomy_and_agent_definitions.sql
-- ============================================================
INSERT INTO jobhub_taxonomy.taxonomy_types(code,name,description)
VALUES
('INDUSTRY','Industry','Controlled industry classification'),
('FUNCTION','Job Function','Controlled functional classification'),
('EMPLOYMENT_TYPE','Employment Type','Full-time, contract, internship etc.'),
('WORK_MODE','Work Mode','Remote, hybrid and on-site'),
('SENIORITY','Seniority','Experience/seniority level'),
('EDUCATION_LEVEL','Education Level','Education expectations'),
('COUNTRY','Country','Country/market taxonomy')
ON CONFLICT (code) DO NOTHING;

INSERT INTO jobhub_taxonomy.taxonomy_values(taxonomy_type_id,code,label)
SELECT id,'REMOTE','Remote' FROM jobhub_taxonomy.taxonomy_types WHERE code='WORK_MODE'
ON CONFLICT DO NOTHING;
INSERT INTO jobhub_taxonomy.taxonomy_values(taxonomy_type_id,code,label)
SELECT id,'HYBRID','Hybrid' FROM jobhub_taxonomy.taxonomy_types WHERE code='WORK_MODE'
ON CONFLICT DO NOTHING;
INSERT INTO jobhub_taxonomy.taxonomy_values(taxonomy_type_id,code,label)
SELECT id,'ONSITE','On-site' FROM jobhub_taxonomy.taxonomy_types WHERE code='WORK_MODE'
ON CONFLICT DO NOTHING;
INSERT INTO jobhub_taxonomy.taxonomy_values(taxonomy_type_id,code,label)
SELECT id,'FULL_TIME','Full Time' FROM jobhub_taxonomy.taxonomy_types WHERE code='EMPLOYMENT_TYPE'
ON CONFLICT DO NOTHING;
INSERT INTO jobhub_taxonomy.taxonomy_values(taxonomy_type_id,code,label)
SELECT id,'PART_TIME','Part Time' FROM jobhub_taxonomy.taxonomy_types WHERE code='EMPLOYMENT_TYPE'
ON CONFLICT DO NOTHING;
INSERT INTO jobhub_taxonomy.taxonomy_values(taxonomy_type_id,code,label)
SELECT id,'CONTRACT','Contract' FROM jobhub_taxonomy.taxonomy_types WHERE code='EMPLOYMENT_TYPE'
ON CONFLICT DO NOTHING;
INSERT INTO jobhub_taxonomy.taxonomy_values(taxonomy_type_id,code,label)
SELECT id,'INTERNSHIP','Internship' FROM jobhub_taxonomy.taxonomy_types WHERE code='EMPLOYMENT_TYPE'
ON CONFLICT DO NOTHING;

INSERT INTO jobhub_ai.agent_definitions(agent_key,name,purpose,version_no)
VALUES
('job-enrichment-orchestrator','Job Enrichment Orchestrator','Coordinates job validation and enrichment specialists.','1.0'),
('job-validation','Job Validation Agent','Determines whether an ingested record is a valid job posting.','1.0'),
('job-duplicate','Job Duplicate Agent','Evaluates potential duplicate jobs using deterministic candidates and semantic evidence.','1.0'),
('job-metadata','Job Metadata Agent','Extracts normalized job metadata from raw job content.','1.0'),
('job-skills','Job Skills Agent','Extracts required/preferred skills and evidence.','1.0'),
('job-taxonomy','Job Taxonomy Agent','Maps extracted concepts to controlled JobHub taxonomy.','1.0'),
('job-quality','Job Quality Agent','Scores quality, completeness and review requirements.','1.0'),
('resume','Resume Agent','Extracts structured candidate data from resumes.','1.0'),
('matching','Job Matching Agent','Explains candidate-job fit using deterministic ranking inputs.','1.0'),
('career-assistant','Career Assistant','Conversational career guidance using approved specialist tools.','1.0')
ON CONFLICT (agent_key) DO NOTHING;
