# JobHub Agentic Multi-Agent Platform

Phase 0 + Phase 1 runnable foundation based on the approved JobHub LLD.

## Scope implemented

- Monorepo structure for Web, Platform API, Agent Runtime, MCP, workflow, docs and infrastructure.
- PostgreSQL foundation with Flyway migrations.
- Tenant, user, role, permission, user-role, role-permission model.
- Local demo JWT authentication for development; production OIDC/JWT boundary is documented.
- Backend RBAC with method-level authorization.
- Audit events and PostgreSQL Outbox events in the same transaction.
- Data-flow smoke path: login -> user lookup -> audit event -> outbox event -> publisher -> published status.
- Spring Boot health/metrics endpoints.
- Flowable BPMN/DMN starter included and a process-definition folder reserved for Phase 2 workflows.
- Next.js 16.3 web shell with JobHub visual language, login, persona-aware portal and API health state.
- Python OpenAI Agents SDK runtime scaffold for the Phase 2 agentic pipeline.
- GitHub Actions CI skeleton.
- Codex instructions in `AGENTS.md`.

## Important boundary

Phase 0/1 deliberately does not implement the full job ingestion/enrichment pipeline. It creates the durable foundation and the identity/RBAC + event data-flow primitives required before Phase 2 ingestion. The existing UI prototype is preserved at `/reference/jobhub_portal.html`.

## Prerequisites

- JDK 21
- Maven 3.9+
- Node.js 22 LTS/current supported runtime
- Python 3.12+
- Docker Desktop/Podman

## Quick start

### Option A — full stack with Docker

```bash
docker compose up --build
```

Web: http://localhost:3000
API: http://localhost:8080
Agent runtime: http://localhost:8090/health

### Option B — run services from the host

#### 1. Start PostgreSQL + pgvector

```bash
docker compose up -d postgres
```

### 2. Start the Platform API

```bash
cd apps/platform-api
../mvnw spring-boot:run
```

Or, if Maven is installed:

```bash
mvn spring-boot:run
```

API: http://localhost:8080
Health: http://localhost:8080/actuator/health

### 3. Start the web app

```bash
cd apps/web
npm install
npm run dev
```

Web: http://localhost:3000

### 4. Start the agent runtime

```bash
cd apps/agent-runtime
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn jobhub_agents.main:app --reload --port 8090
```

Agent health: http://localhost:8090/health

## Demo accounts

All demo passwords are `password` and are created on first API startup.

| Persona | Email |
|---|---|
| Job Seeker | `seeker@jobhub.local` |
| Student / Fresher | `fresher@jobhub.local` |
| Working Professional | `professional@jobhub.local` |
| Recruiter | `recruiter@jobhub.local` |
| Employer | `employer@jobhub.local` |
| Admin | `admin@jobhub.local` |

## Data-flow smoke test

1. Open the web app.
2. Sign in as `admin@jobhub.local` / `password`.
3. The frontend calls `POST /api/v1/auth/demo-login`.
4. The API validates the user and tenant from PostgreSQL.
5. The API creates an audit record and `USER_LOGIN` outbox record in one transaction.
6. The scheduled outbox publisher marks the record as published.
7. `/api/v1/admin/dataflow` shows users, audit and outbox counts.

## Phase 2 extension point

The next vertical slice will add `JOB_RECEIVED` to the Outbox, start Flowable `JobEnrichmentProcess(jobRawId)`, call the OpenAI Agents SDK runtime, and persist the structured enrichment result. This follows the approved LLD data flow.
