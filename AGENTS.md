# JobHub Codex Rules

**This repo contains two generations of the project; only `poc/` is live.** The original
Spring Boot/Next.js/Postgres stack under `apps/` (rules further below) was scrapped as the
active runtime surface on 2026-09-16 for a minimal Python pipeline under `poc/` (scraper →
SQLite → Flask+TS web app → WhatsApp alerts) — see `CLAUDE.md` for the full picture and
`poc/PLAN.md`/`poc/README.md` for pivot rationale and architecture. `apps/` source is left
untouched in git history but is not deployed and should not be extended without being asked.
The original Low-Level Design under `artifacts/` describes an even larger target
architecture (Flowable, a Python agent-runtime, MCP tool boundaries) that was never built at
all — further from reality than `apps/` itself, historical/aspirational only.

## Architecture rules (`poc/` — the live system)

1. Flask (`poc/jobhub_poc/webapp/`) owns the web app; routes stay thin blueprints
   (`auth`, `routes_jobs`, `routes_alerts`, `routes_api`) — business logic (loading,
   purging, alert matching) lives in `loader/` and `alerts/`, not scattered into handlers.
2. SQLite (`poc/jobhub_poc/schema.sql`) is the system of record — plain `sqlite3` +
   parameterized SQL throughout, no ORM. Keep it that way; don't introduce one for a POC.
3. There is no LLM/agent enrichment layer in `poc/`. Jobs are stored as scraped
   (`raw_json` verbatim); there is no confidence-scoring or agentic pass equivalent to
   `apps/`'s `JobEnrichmentAgent`. Don't assume one exists.
4. Freshness/purge is keyed **solely on `first_seen_at`**, set once at insert and never
   touched on update. Never key purge or "new job" detection off the source's own
   `datePosted` (unreliable — ranges 2021–2026 in real data) or off `last_seen_at`.
5. EverJobs' `query`/`results` request params are **not honored server-side** — a scrape
   call returns everything for a site bucket regardless of search term. Filtering/capping by
   `SEARCH_TERMS`/`RESULTS_PER_TERM` must happen client-side in `dump_jobs.py`, not by
   trusting the request params to do it.
6. Alert sends must stay idempotent — `alerts_sent` has `UNIQUE(subscription_id, job_id)`.
   Any new send path must respect that constraint, not bypass or duplicate it.
7. `NOTIFIER_BACKEND` (`console` | `whatsapp`) is the only supported way to switch alert
   delivery, via `get_notifier()` — don't hardcode a backend choice in calling code.
8. One shared demo login (`app_users`, seeded by `scripts/seed_demo_user.py`) — there are no
   per-user accounts, roles, or RBAC in `poc/`. Don't assume any exist.
9. Everything is env-configured (hosts, ports, keys, paths) per `poc/.env.example` and
   `poc/scraper/.env` — no hardcoded hosts/ports/keys, since a future move off the current
   pi05/pi09 hosts is expected. The pipeline runs entirely on those two (pi09 orchestrates
   itself, pulling directly from pi05) as of 2026-09-22 — no third host is involved.
10. Never commit secrets. `poc/.env`, `poc/whatsapp-sender/.env`, and
    `poc/whatsapp-sender/auth_info/` (the live WhatsApp session) are gitignored — keep them
    that way.

## Architecture rules (`apps/` — retired stack, not deployed)

1. Spring Boot owns business logic, APIs, authorization, persistence and audit.
2. There is no Flowable and no BPMN/DMN engine. `workflow/dmn` and `workflow/processes`
   are empty placeholders. `Job.status` is a plain string defaulting to `"DRAFT"` with no
   transition logic anywhere — if you need gating/state transitions, you're building them
   from scratch, not plugging into an existing engine.
3. Agents run in-process inside `platform-api`, not as a separate service. `JobEnrichmentAgent`
   is a normal Spring `@Service` that calls Ollama's `/api/generate` over REST and reads/writes
   repositories directly — there is no agent-runtime process, no OpenAI Agents SDK, and no
   MCP tool boundary. Don't build against an MCP/tool abstraction that isn't there.
4. PostgreSQL is the system of record.
5. Raw ingestion JSON is already immutable today, not a future-phase addition: `jobs_raw`
   (`JobRaw` entity) stores `payload` + `payload_hash` and is never updated after insert.
6. All writes are authorized and audited in principle, but verify before assuming a given
   endpoint is protected — `SecurityConfig` currently `permitAll()`s `/api/v1/admin/**` and
   `/api/v1/jobs/**` at the gateway, so those paths rely solely on method-level
   `@PreAuthorize`. `AuditService` is wired into `AuthService` only; ingestion/enrichment
   writes are not currently audited. Don't extend the permitAll() list further without a
   reason, and prefer adding audit calls to new write paths rather than assuming they exist.
7. Flyway is present as a dependency but **disabled** (`spring.flyway.enabled: false`).
   Schema changes currently happen via Hibernate `ddl-auto: update` against `@Entity`
   classes; `V1__foundation.sql` / `V2__seed_rbac.sql` do not run and are stale. If a task
   requires a real migration path, re-enabling Flyway (and reconciling those SQL files with
   the live schema) is part of the task, not a given.
8. Ingestion idempotency today is a simple existence check
   (`existsBySourceIdAndExternalJobId`) before insert, not a formal
   `JOB_ENRICHMENT:{jobRawId}:{payloadHash}`-style idempotency key. Keep new async writes at
   least this idempotent; a hash-based key is an improvement, not a regression, if you add one.
9. Prefer structured JSON contracts between services (Java DTOs / Jackson here — there's no
   Python side, so no Pydantic).
10. Do not add Kafka, OpenSearch or Kubernetes before the relevant phase acceptance criteria pass.
11. Never commit secrets. `.env` is gitignored; `.env.example` is the template.
12. Never bypass RBAC for convenience — and don't widen `permitAll()` to work around it.

## Coding loop

Before coding: inspect the relevant module and state a small implementation plan.

During coding: change one vertical slice; reuse existing services; avoid unrelated refactors.

After coding: run formatting/static checks, unit tests, integration tests when available, and the documented smoke test.

## Delivery format for every Codex task

- Files changed
- Design decision
- Tests added/run
- Commands to run
- Acceptance criteria status
- Known limitations
