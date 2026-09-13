# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

JobHub is an **Agentic / Multi-Agent Job Intelligence Platform**. It ingests jobs from multiple sources, enriches them through an AI agent pipeline (deduplication, metadata extraction, skill extraction, taxonomy resolution, quality assessment, embedding), gates publication through deterministic workflow, and matches candidates semantically.

The current repository is in **pre-implementation / early foundation** state. Most substantive content lives in design artifacts under `artifacts/` and a zip scaffold under `artifacts/_unzipped/jobhub-agentic/`. The working tree itself is mostly empty (no application source at root yet).

## Three Phase Systems — Do Not Confuse These

| Label | Meaning | Scope |
|---|---|---|
| **WhatsApp "Phase 0+1"** (delivery plan) | 2-week MVP slice | Foundation → first E2E: Login → Ingest → Enrich → Review → Search → Match |
| **LLD Phases 0–13** (`artifacts/JobHub_Agentic_MultiAgent_Low_Level_Design_v1.0.md` Table 23) | Full engineering roadmap | 0 Foundation … 13 Scale |
| **Product Phase 1 / Phase 2** (E2E deck PDF) | MVP vs Scale-Up | P1 = local/containers, JWT, pgvector, Flowable in-process; P2 = Kafka, OpenSearch, Keycloak, K8s, WhatsApp |

The 2-week delivery target is the **WhatsApp slice**, not the full LLD.

## Current Implementation State

The scaffold at `artifacts/_unzipped/jobhub-agentic/` implements **LLD Phase 0 + Phase 1 only**:
- Monorepo structure (`apps/web`, `apps/platform-api`, `apps/agent-runtime`)
- PostgreSQL foundation via Flyway (V1 foundation, V2 seed RBAC)
- Tenant/user/role/permission model
- Demo JWT auth for all 6 personas
- Method-level RBAC with `@PreAuthorize`
- Audit events + PostgreSQL Outbox in same transaction
- Spring Boot 4.1.1 + Actuator health/metrics
- Flowable 8.0 BPMN/DMN starter (process/dmn folders reserved, no processes yet)
- Next.js 16.3 web shell (login + persona-aware portal)
- Python agent runtime stub (health endpoint + NOT_IMPLEMENTED enrichment endpoint)
- GitHub Actions CI (web build + api tests)

The agent runtime, job ingestion, enrichment pipeline, search, and matching are **NOT yet implemented**.

## Technology Stack

| Layer | Technology | Version |
|---|---|---|
| Backend API | Java + Spring Boot | Java 21, Spring Boot 4.1.1 |
| Workflow | Flowable BPMN/DMN | 8.0.0 |
| Agent Runtime | Python + OpenAI Agents SDK | Python 3.12+, openai-agents 0.22.1 |
| Frontend | Next.js (React) | Next.js 16.3.4, React 19.2 |
| Database | PostgreSQL + pgvector | pgvector/pgvector:pg17 |
| Migrations | Flyway | via Spring Boot starter |
| Build (Java) | Maven | 3.9+ (wrapper `mvnw` included) |
| Build (web) | npm | Node 22 LTS |
| Containers | Docker Compose | — |

**Stack authority**: LLD + zip scaffold win (Java Spring + Python OpenAI Agents SDK + Next.js). The E2E Platform PDF mentions Spring AI / ReactJS / Kong / Keycloak — that is product vision language, not the current implementation contract.

## Architecture Rules (from AGENTS.md)

1. Spring Boot owns business logic, APIs, authorization, persistence, and audit.
2. Flowable owns business process state, human tasks, retries, and deterministic gates.
3. Agents reason and recommend; they do **not** directly access PostgreSQL.
4. Agent tools/MCP are the only agent capability boundary.
5. PostgreSQL is the system of record. Agent sessions/traces are operational state only.
6. Raw ingestion JSON is immutable.
7. All writes are authorized and audited.
8. Use Flyway for schema changes — never ad-hoc DDL.
9. Use idempotency for asynchronous operations (key = `JOB_ENRICHMENT:{jobRawId}:{payloadHash}`).
10. Prefer structured JSON contracts between services (Pydantic in Python, DTOs in Java).
11. Do **not** add Kafka, OpenSearch, or Kubernetes before the relevant phase acceptance criteria pass.
12. Never commit secrets. `.env` is gitignored; use `.env.example` as template.
13. Never bypass RBAC for convenience.

## Key Domain Concepts

- **jobs_raw**: Immutable source records with `payload_hash` for idempotency. Never updated after insert.
- **jobs**: Canonical, enriched, user-visible jobs. Created only after enrichment gate passes.
- **ai_processing_runs**: Audit trail of every agent run (agent name, version, model, prompt version, input hash, output JSON, confidence, trace_id).
- **Outbox pattern**: Business events written atomically in the same transaction as state changes; a scheduled publisher marks them delivered. This is the reliable event mechanism before Kafka.
- **DMN confidence gate**: After enrichment, a DMN decision table routes to PUBLISH (confidence ≥ 0.90), REVIEW (lower confidence), or DUPLICATE. Thresholds live in DMN/config, not in agent prompts.
- **Matching formula**: `0.30*keyword + 0.25*semantic + 0.15*skill + 0.10*experience + 0.10*location + 0.05*freshness + 0.05*preference`. Version stored with match records.
- **Tenant isolation**: Shared schema + `tenant_id` column + app-level filters (Product P1 level). No RLS or schema-per-tenant yet.
- **MCP servers** (planned): job, candidate, resume, search, taxonomy, workflow, analytics, learning, notification. Agents consume these, never raw DB.

## Build & Run Commands

### Full stack via Docker
```bash
docker compose up --build
```
- Web: http://localhost:3000
- API: http://localhost:8080
- Agent runtime: http://localhost:8090/health

### Run services from host (development)

```bash
# 1. Infrastructure
docker compose up -d postgres

# 2. API (from apps/platform-api)
./mvnw spring-boot:run
# Health: http://localhost:8080/actuator/health

# 3. Web (from apps/web)
npm install && npm run dev

# 4. Agent runtime (from apps/agent-runtime)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn jobhub_agents.main:app --reload --port 8090
```

### Shortcuts via Makefile (from repo root)
```bash
make up          # docker compose up -d --build
make run-api     # start platform-api
make run-web     # start web
make run-agent   # start agent runtime
make smoke       # run scripts/smoke-test.sh
make down        # docker compose down
```

### Run API tests
```bash
cd apps/platform-api
mvn test
```

### Run a single test class
```bash
cd apps/platform-api
mvn test -Dtest=AuthControllerTest
```

## Demo Accounts

All passwords are `password`, created on first API startup by `DemoDataSeeder`.

| Persona | Email |
|---|---|
| Job Seeker | seeker@jobhub.local |
| Student / Fresher | fresher@jobhub.local |
| Working Professional | professional@jobhub.local |
| Recruiter | recruiter@jobhub.local |
| Employer | employer@jobhub.local |
| Admin | admin@jobhub.local |

## Smoke Test

`scripts/smoke-test.sh` exercises the data-flow path: admin login → JWT issued → `/me` returns identity → admin-only endpoint returns 200 → seeker hitting same endpoint returns 403.

## Key Environment Variables

Defined in `.env.example` and consumed via `application.yml`:
- `JOBHUB_DB_URL`, `JOBHUB_DB_USER`, `JOBHUB_DB_PASSWORD` — PostgreSQL connection
- `JOBHUB_JWT_SECRET` — dev JWT signing secret (change in any non-local env)
- `JOBHUB_WEB_ORIGIN` — CORS allowed origin
- `OPENAI_API_KEY`, `OPENAI_MODEL` — agent runtime

## Database Schema Notes

- `artifacts/JobHub_Complete_PostgreSQL_Schema_v1.0.sql` (1188 lines) is the **target** schema reference. Do not dump it wholesale into early migrations — add tables incrementally via Flyway as features need them.
- Database init script `database/init/01-extensions.sql` enables pgvector.
- Migration files: `apps/platform-api/src/main/resources/db/migration/V1__foundation.sql`, `V2__seed_rbac.sql`.
- Schemas: `jobhub` (canonical), `jobhub_taxonomy`, `jobhub_ai`, `jobhub_user`, `jobhub_notification`, `jobhub_analytics`, `flowable`.

## 2-Week Delivery Scope (WhatsApp)

**In scope:** Login → Ingest → Enrich → Review → Search → Match, demonstrable via `docker compose up` with Madhu driving.

**Explicitly OUT:** full agent catalog (~22 agents), Kafka/OpenSearch/Kubernetes, production multi-tenant hardening, recruiter/employer copilots, deep UI polish, EverJobs 160-source connector farm.

## Repository Structure (target, after scaffold import)

```
jobhub/
  apps/
    web/                    # Next.js 16 portal
    platform-api/           # Java 21 + Spring Boot (Maven)
    agent-runtime/          # Python + OpenAI Agents SDK (FastAPI/uvicorn)
  mcp/                      # Domain MCP servers (planned)
  workflow/
    bpmn/                   # Flowable process definitions
    dmn/                    # Decision tables
  database/
    migrations/             # Flyway scripts
    init/                   # Postgres init (extensions)
  infra/
    docker/
    observability/
  docs/
    architecture/
    runbooks/
  artifacts/                # Design docs, prototypes, task boards
  CLAUDE.md
  AGENTS.md
  README.md
  docker-compose.yml
  Makefile
```

## Java Package Structure (inside platform-api)

`com.jobhub.platform` with sub-packages: `auth`, `common` (audit, outbox, exception handling), and per-domain packages to be added (ingestion, jobs, taxonomy, candidates, resumes, matching, workflow, etc.). Layering: Controller → Application Service → Domain Service → Repository/Client. Spring Security + `@PreAuthorize` for authorization.

## Python Agent Runtime Structure (planned expansion)

`jobhub_agents/` with `agents/` (orchestrator + specialists), `tools/`, `schemas/` (Pydantic), `guardrails/`, `prompts/`, `sessions/`, `evaluations/`, `tracing/`, and `main.py` (FastAPI entry). Currently only `main.py` with a stub enrichment endpoint exists.

## Important Boundaries

- The `artifacts/` directory contains design authority documents and prototypes. The LLD v1.0 MD is the implementation contract.
- `tasks_all.md` and `tasks_sanjay.md` are task boards — not specification, but contain scope decisions and open questions.
- `memory/` holds session memory files for continuity across Claude sessions.
- The agent runtime must never receive DB credentials. All data access flows through tools/MCP.
- Frontend menu hiding is UX convenience only; Spring Security is the authorization authority.
