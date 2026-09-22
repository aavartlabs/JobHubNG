# JobHubNG

Job intelligence pipeline: scrapes jobs from EverJobs, stores them in SQLite, serves them
through a small login-gated web app, and sends WhatsApp alerts on matches. Live at
https://jobhubs.aavartlabs.com.

**This repo contains two generations of the project — only `poc/` is live.** The original
Spring Boot/Next.js/Postgres stack under `apps/` was scrapped as the active runtime surface
on 2026-09-16; its source is kept in git history but nothing under `apps/` is deployed. See
[Retired stack](#retired-stack-apps) below, and `CLAUDE.md` for the full picture.

## Quick Start (`poc/` — the live system)

```bash
cd poc
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env       # edit as needed
.venv/bin/pytest -v        # 33 tests

cd scraper
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pytest -v        # 10 tests, separate venv/deps
```

Run against the bundled real fixture without a live scraper:
```bash
cd poc
.venv/bin/python scripts/seed_demo_data.py     # loads fixtures/sample_everjobs_response_real.json
.venv/bin/python -m jobhub_poc.webapp.app      # http://localhost:8100/jobs
```

Job browsing is public. Real self-service accounts (email + password + mobile, both
verified by OTP) live in `poc/auth-service/`, a companion Better Auth service that Flask
proxies `/auth/*` to; they gate `/alerts/*` only. See `docs/rbac.md`.

## Architecture

```
pi05: scraper/                          pi09: jobhub_poc/  (Docker container "jobhub-web")
  EverJobs (prebuilt Node dist)            loader/   JSON dump -> SQLite (dedupe, purge)
  dump_jobs.py --json dump--------------->  webapp/   Flask JSON API + TS frontend, login-gated
                                             alerts/   registration + matcher + notifier
                                             (pi09 pulls directly, no relay host)

https://jobhubs.aavartlabs.com --(Cloudflare Tunnel, fixed target jobhub-web:3000)--> pi09
```

**Stack:** Python (Flask + a small esbuild-bundled TypeScript frontend, no framework) +
SQLite, no ORM. EverJobs (external, prebuilt Node scraper, not in this repo) runs only on
pi05; the web app, loader, and alert logic run only on pi09; `poc/scripts/run_pipeline.sh`
runs on pi09 itself, orchestrating scrape → load → purge → alert on a systemd timer every 6
hours — the whole pipeline runs entirely on always-on Raspberry Pi hardware, no third host
involved. Alerts send via WhatsApp through a hand-rolled `poc/whatsapp-sender/` gateway
(`baileys`), idempotent on `(subscription_id, job_id)`. There is no LLM/agent enrichment
step and no RBAC — one shared demo login. Full detail: `poc/README.md` and `poc/PLAN.md`.

See `CLAUDE.md` for the fuller architecture breakdown, environment variables, and Codex/
Claude-specific guidance.

## Retired stack (`apps/`)

Not deployed, not extended, kept for context only.

```bash
cp .env.example .env
# Point OLLAMA_BASE_URL at a reachable Ollama host and EVER_JOBS_API_URL at a running
# EverJobs instance (both are external services, not started by this compose file)
docker compose up --build
```
- API: http://localhost:8080 · Web: http://localhost:3001

```bash
cd apps/platform-api && ./mvnw spring-boot:run   # backend only
cd apps/web && npm install && npm run dev        # frontend only
cd apps/platform-api && mvn test                 # backend tests, H2 not Postgres
bash scripts/smoke-test.sh                       # requires the API already running
```

**Stack:** Java 21 + Spring Boot 3.3 + Spring Data JPA · Next.js 16 (App Router, JS not TS)
· PostgreSQL 16 + pgvector · Spring Security + a self-issued JWT (no external IdP) · one
Spring service (`JobEnrichmentAgent`) calling Ollama's `/api/generate` directly — no Spring
AI, no agent framework, no workflow engine.

Demo accounts (all password `password`): `{seeker,fresher,professional,recruiter,employer,
admin}@jobhub.local`.

There's no frontend test suite — CI only runs `npm run build` for `apps/web`. See
`CLAUDE.md` for a fuller breakdown and known gaps between this stack and the original
design docs under `artifacts/`.
