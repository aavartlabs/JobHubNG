# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

JobHubNG is an agentic job intelligence platform: it scrapes/ingests jobs from an external
service (EverJobs), enriches raw postings via an LLM call, and serves them through a
Next.js portal with role-based demo logins. It is deployed at `jobhubs.aavartlabs.com`
via a Cloudflare Tunnel container alongside the app services.

**The implementation has diverged from the original design docs under `artifacts/`.**
Those documents (LLD v1.0, the E2E PDF, `tasks_all.md`, `tasks_sanjay.md`) describe a
larger target architecture — Flowable BPMN/DMN gating, a Python agent-runtime service on
the OpenAI Agents SDK, Kafka/OpenSearch at scale, a full ~22-agent catalog. **None of that
exists in the current codebase.** Treat `artifacts/` as aspirational/historical context,
not a description of what's running. The sections below describe what is actually
implemented; when in doubt, trust the code over `artifacts/`, `AGENTS.md`, or `README.md`,
which still describe the older target design in places.

## Actual Architecture (as implemented)

```
Next.js 16 web portal  →  Spring Boot 3.3 platform-api  →  PostgreSQL 16 + pgvector
                                    ↓
                          Ollama (self-hosted LLM, called directly over HTTP)
                                    ↑
                          EverJobs (external NestJS scraper service, not in this repo)
```

- **No agent-runtime service.** There is no Python service, no OpenAI Agents SDK, no MCP
  servers. `apps/agent-runtime` does not exist even though `Makefile`'s `run-agent` target
  and parts of the sibling docs still reference it as if it does.
- **No Flowable.** `workflow/dmn` and `workflow/processes` (under `apps/platform-api/src/main/resources`)
  contain only placeholder `README.txt` files, and Flowable is not a Maven dependency.
  Enrichment is a plain synchronous service call, not a BPMN process. There is no
  confidence-gate DMN table; `JobEnrichmentAgent` just records a `confidence` field in the
  JSON it gets back from the model.
- **Enrichment = one Java service calling Ollama's `/api/generate` over REST.**
  See `apps/platform-api/.../service/JobEnrichmentAgent.java`. It prompts for a JSON blob,
  strips markdown fences, parses it, and records an `AiProcessingRun` row either way
  (`SUCCESS` or `FAILED`). There is no retry/guardrail layer.
- **Ingestion pulls from EverJobs**, an external NestJS scraper reached over HTTP
  (`EverJobsClient` → `EVER_JOBS_API_URL`, header `x-api-key`). It is **not part of this
  repo** — `ever-jobs-docker/` here is only a deploy `Dockerfile`/`package.json` for
  pushing a prebuilt `dist/` of that other project; there's no EverJobs source checked in.
  `IngestionScheduler` runs it hourly via `@Scheduled(cron=...)`, driven by the
  `ingestion.keywords` list in `application.yml`. `JobIngestionService.ingestKeyword`
  currently hardcodes `sourceId = 1L`.
- **Flyway migrations exist but are inert.** `application.yml` sets
  `spring.flyway.enabled: false` and `jpa.hibernate.ddl-auto: update`. The Postgres schemas
  (`jobhub`, `jobhub_ai`) are created once by `database/init/01-extensions.sql` on first
  container start (Docker Postgres init-script mechanism, not Flyway), and all table DDL
  after that is Hibernate auto-DDL driven by the `@Entity` classes. `V1__foundation.sql`
  and `V2__seed_rbac.sql` under `db/migration/` are **not executed** and are stale relative
  to the real schema — don't treat them as ground truth, and don't assume a new `V3__*.sql`
  file will do anything unless you first re-enable Flyway. RBAC seed data instead comes
  from `DemoDataSeeder` (Java, `@EventListener(ApplicationReadyEvent.class)`), which is
  idempotent by checking `tenantRepository.count() > 0`.
- **Auth**: Spring Security + a self-issued HS256 JWT (Nimbus `JwtEncoder`/`JwtDecoder`
  over an `HmacSHA256` key derived from `jobhub.security.jwt-secret`), not an external IdP.
  Login is `/api/v1/auth/demo-login` (email/password against demo accounts, BCrypt).
  `SecurityConfig` `permitAll()`s `/actuator/**`, `/api/v1/auth/demo-login`,
  `/api/v1/public/**`, and — notably — `/api/v1/jobs/**` and `/api/v1/admin/**` at the
  gateway; anything gated under those paths (e.g. `/api/v1/admin/dataflow`) relies solely
  on method-level `@PreAuthorize`, not on the security filter chain. Know this before
  assuming a path prefix implies auth.
- **Tenant isolation**: shared schema + `tenant_id` column, app-level filtering only. No RLS.

## Build & Run Commands

### Full stack via Docker
```bash
cp .env.example .env   # set OLLAMA_BASE_URL / EVER_JOBS_API_URL for your environment
docker compose up --build
```
- Web: http://localhost:3001 (container maps host 3001 → container 3000)
- API: http://localhost:8080
- Postgres: localhost:5432 (`pgvector/pgvector:pg16`, db/user/pass all `jobhub`)

There is also a `cloudflare-tunnel` service in `docker-compose.yml` for exposing `web` at
`jobhubs.aavartlabs.com`; it needs `CLOUDFLARE_TUNNEL_TOKEN` and only matters for the real
deployment, not local dev.

### Run services individually (development)
```bash
# Postgres only
docker compose up -d postgres

# API (from apps/platform-api) — http://localhost:8080/actuator/health
cd apps/platform-api && ./mvnw spring-boot:run

# Web (from apps/web) — Next.js dev server on :3000
cd apps/web && npm install && npm run dev
```

### Makefile shortcuts (repo root)
```bash
make up          # docker compose up -d --build
make run-api     # start platform-api
make run-web     # start web
make smoke       # run scripts/smoke-test.sh
make down        # docker compose down
```
`make run-agent` exists in the `Makefile` but targets `apps/agent-runtime`, which does not
exist in this repo — it will fail if invoked.

### Tests
```bash
cd apps/platform-api
mvn test                              # full suite, runs against in-memory H2 (application-test.yml), not Postgres
mvn test -Dtest=AuthControllerTest    # single class
mvn test -Dtest=JobIngestionServiceTest
```
There is no web/JS test suite — CI only runs `npm run build` for `apps/web` (see
`.github/workflows/ci.yml`), no `npm test`.

### Smoke test
`scripts/smoke-test.sh` (bash+curl+python3) hits a running API: admin `demo-login` → JWT →
`/auth/me` → `/admin/dataflow` returns 200 for admin, then confirms the same endpoint
returns 403 for a seeker token. Requires the API to already be running
(`JOBHUB_API_URL`, default `http://localhost:8080`).

## Demo Accounts

All passwords are `password`, seeded on first API startup by `DemoDataSeeder` (skipped if
any tenant row already exists — delete the Postgres volume to reseed).

| Persona | Email |
|---|---|
| Job Seeker | seeker@jobhub.local |
| Student / Fresher | fresher@jobhub.local |
| Working Professional | professional@jobhub.local |
| Recruiter | recruiter@jobhub.local |
| Employer | employer@jobhub.local |
| Admin | admin@jobhub.local |

## Java Package Structure (`apps/platform-api`)

Flat by layer, not by domain: `com.jobhub.platform.{config, controller, domain, repository,
service}`. There is no per-feature package split (no `ingestion/`, `jobs/`, `taxonomy/`
sub-packages) despite what older docs describe — everything of a given layer lives in one
package regardless of feature area. Controllers are thin; most logic sits directly in
`service/*Service.java` / `*Agent.java` classes calling repositories.

Notable controllers and their path prefixes:
- `AuthController` — `/api/v1/auth/*`, `/api/v1/admin/dataflow`, `/api/v1/public/ping`
- `JobSearchController` — `/api/v1/jobs/*` (public-facing search/detail)
- `IngestionController` — `/api/v1/admin/ingestion/*` (manual trigger + health)
- `SweepController` — `/api/v1/admin/sweep/*`
- `JobController` — `/internal/v1/*`, used for system-to-system calls
  (`ingestion/jobs` requires `ROLE_ADMIN`, `agent-runs/job-enrichment` requires
  `ROLE_SYSTEM`)
- `PlatformController` — `/api/v1/ops/health`

## Key Environment Variables (`.env.example`)

- `JOBHUB_DB_URL` / `JOBHUB_DB_USER` / `JOBHUB_DB_PASSWORD` — Postgres connection
- `JOBHUB_JWT_SECRET` — HS256 signing key; change outside local dev
- `JOBHUB_WEB_ORIGIN` — CORS allowed origin (defaults to the production domain, not localhost)
- `OLLAMA_BASE_URL` / `OLLAMA_MODEL` — self-hosted LLM used for enrichment (currently
  points at a LAN host, e.g. `192.168.2.106:11434`, model `ministral-3:14b`); **not**
  `OPENAI_API_KEY` despite what some `artifacts/` docs assume
- `EVER_JOBS_API_URL` / `EVER_JOBS_API_KEY` — external scraper service; the host in
  `.env.example` and the default in `docker-compose.yml` currently disagree (a GCP VM vs.
  a `192.168.2.x` LAN host) — confirm which is live before relying on ingestion working
- `NEXT_PUBLIC_API_BASE_URL` — what the browser uses to reach the API
- `CLOUDFLARE_TUNNEL_TOKEN` — only needed for the `cloudflare-tunnel` compose service

## Important Boundaries

- `artifacts/` holds design authority docs and an earlier zip scaffold
  (`artifacts/_unzipped/jobhub-agentic/`) — useful for understanding long-term intent, but
  do not assume anything there is wired up; verify against the actual `apps/` tree first.
- `AGENTS.md` and `README.md` at the repo root also describe the target/earlier design
  (Flowable, Spring AI, OpenAI) rather than the current implementation — prefer this file
  and the code when they conflict.
- `tasks_all.md` / `tasks_sanjay.md` are task boards, not specifications, but do capture
  scope decisions and open questions worth checking before assuming something is unscoped.
- `memory/` holds session memory files for continuity across Claude sessions.
- `docs/data-flow.md`, `docs/rbac.md`, `docs/runbook.md` describe specific subsystems in
  more depth than this file.
