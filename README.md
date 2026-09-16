# JobHubNG

Agentic Job Intelligence Platform.

## Quick Start

```bash
cp .env.example .env
# Point OLLAMA_BASE_URL at a reachable Ollama host and EVER_JOBS_API_URL at a running
# EverJobs instance (both are external services, not started by this compose file)
docker compose up --build
```

- API: http://localhost:8080
- Web: http://localhost:3001 (via `docker compose`; the Next.js dev server on
  `npm run dev` instead serves :3000 directly)

Enrichment and ingestion will no-op or log errors if `OLLAMA_BASE_URL` / `EVER_JOBS_API_URL`
aren't reachable — everything else (auth, browsing already-seeded jobs) still works.

## Demo Accounts

| Persona | Email | Password |
|---------|-------|----------|
| Admin | admin@jobhub.local | password |
| Seeker | seeker@jobhub.local | password |
| Fresher | fresher@jobhub.local | password |
| Professional | professional@jobhub.local | password |
| Recruiter | recruiter@jobhub.local | password |
| Employer | employer@jobhub.local | password |

## Architecture

```
Next.js 16 → Spring Boot 3.3 → PostgreSQL 16 + pgvector
                    ↓
            Ollama (self-hosted LLM, called directly over REST — no Spring AI, no agent framework)
                    ↑
            EverJobs (external scraper service, not in this repo)
```

**Stack:**
- **Backend:** Java 21 + Spring Boot 3.3 + Spring Data JPA
- **Frontend:** Next.js 16 (App Router, JS not TS)
- **Database:** PostgreSQL 16 + pgvector
- **Auth:** Spring Security + a self-issued JWT (no external IdP)
- **AI:** one Spring service (`JobEnrichmentAgent`) calling Ollama's `/api/generate` — no
  Spring AI, no OpenAI Agents SDK, no MCP layer
- **Workflow:** none — no Flowable, no state machine. `Job.status` is a plain string field
  defaulting to `"DRAFT"` with no transition logic wired up yet.

## Development

```bash
# Backend only
cd apps/platform-api && ./mvnw spring-boot:run

# Frontend only
cd apps/web && npm install && npm run dev

# Backend tests (run against in-memory H2, not Postgres)
cd apps/platform-api && mvn test

# Smoke test (requires the API already running)
bash scripts/smoke-test.sh
```

There's no frontend test suite yet — CI only runs `npm run build` for `apps/web`.

See `CLAUDE.md` for a fuller architecture breakdown and known gaps between this repo and
the original design docs under `artifacts/`.
