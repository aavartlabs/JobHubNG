# JobHubNG Data Flow

**This repo contains two generations of the project — only `poc/` is live.** See `CLAUDE.md`
for the full picture. The flow below is the current, deployed pipeline; the retired Phase
0/1 Spring Boot flow (`apps/`) is kept further down for context only.

## Live flow (`poc/`)

```text
pi05: EverJobs (Node) <--HTTP-- scraper/dump_jobs.py
                                    |  (one fetch per pipeline run; query/results params
                                    |   aren't honored server-side, so filtering by
                                    |   SEARCH_TERMS/RESULTS_PER_TERM happens here)
                                    v
                          scraper/dumps/*.json   {"jobs": [...]}
                                    |
                  scp: pi05 -> pi09, direct    (scripts/run_pipeline.sh, step 2 of 3)
                                    |
                                    v
pi09: jobhub_poc.loader.load_dump  --upsert on dedupe_key-->  SQLite `jobs` table
        |   first_seen_at set once at insert, never touched again
        |   last_seen_at bumped on every re-load hit
        |   emits the list of genuinely-NEW job ids (not an update)
        v
      jobhub_poc.loader.purge  --deletes rows where first_seen_at < now - PURGE_WINDOW_DAYS
        v
      jobhub_poc.alerts.run_alerts --new-ids <new_ids.json>
        |
        +--> matcher.find_matches(conn, new_ids)
        |       active alert_subscriptions whose title_keyword/location_keyword
        |       substring-match one of the new jobs
        |
        +--> notifier.send(match)   -- idempotent: no-op if (subscription_id, job_id)
                |                       already exists in alerts_sent
                +--> ConsoleNotifier   -- stdout + alerts_sent row (status SENT/FAILED)
                +--> WhatsAppNotifier  -- POST whatsapp-sender:3100/send -> alerts_sent row

Browser --GET /jobs (redirects to /login if unauthenticated)--> Flask webapp
                                                                     |
                                                                     v
                                                       static/app.js (TS, esbuild-bundled)
                                                                     |
                                                                     v
                                                        GET /api/jobs (JSON, paginated,
                                                        title/location filter, freshness/
                                                        title sort) --> SQLite `jobs`
```

Orchestration entrypoint: `poc/scripts/run_pipeline.sh`, run **on pi09 itself** (as of
2026-09-22 — previously relayed through a third host, harita; pi05<->pi09 SSH trust now
exists, so that hop is gone), scheduled automatically every 6 hours via a systemd **user**
timer on pi09. It does not touch the web container — the web app just reads whatever's
currently in SQLite.

## Why this flow is shaped this way

Freshness/purge is keyed **solely on `first_seen_at`**, never the source's own `datePosted`
(real EverJobs data ranges from 2021 to 2026, unusable as a freshness signal) or
`last_seen_at` (would make an evergreen re-posted listing immortal). "New job" detection for
alerts uses the loader's own insert-vs-update return value, not a timestamp-window
heuristic, because a heuristic would either miss jobs or double-fire depending on pipeline
cadence. See `poc/PLAN.md` for the full design rationale, including what was originally
assumed about EverJobs vs. what real scraping confirmed.

## Retired: Phase 0/1 Spring Boot flow (`apps/`, not live)

```text
Browser
  |
  | POST /api/v1/auth/demo-login
  v
Spring Boot AuthController
  |
  v
AuthService
  |
  +--> PostgreSQL users -> roles -> permissions -> tenant
  |
  +--> JWT issued (roles + permissions + tenant)
  |
  +--> AuditOutboxService [single DB transaction]
          |
          +--> audit_events
          |
          +--> outbox_events [PENDING]
                              |
                              v
                        OutboxPublisher
                              |
                              v
                       outbox_events [PUBLISHED]
```

### Why this was the Phase 0/1 data flow

The LLD required durable business state in PostgreSQL, backend-enforced RBAC, auditability
and idempotent asynchronous/event boundaries. The login path exercised these boundaries
without pretending that job ingestion had already been implemented.

### Phase 2 extension (never built, in either stack)

```text
Job Source
 -> Spring Boot Connector
 -> jobs_raw (immutable JSONB)
 -> outbox JOB_RECEIVED
 -> Flowable JobEnrichmentProcess
 -> Agent Runtime / OpenAI Agents SDK
 -> structured JobEnrichmentResult
 -> Flowable DMN
 -> canonical jobs OR human review
 -> embedding
 -> search
```

This was the LLD's target job-enrichment sequence for `apps/`. It was never implemented
there, and the `poc/` pivot replaced the whole idea with a much simpler, non-agentic flow
(see "Live flow" above) rather than building toward it.
