# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

JobHubNG is a job intelligence pipeline: it scrapes jobs from an external service
(EverJobs), stores them in SQLite, serves them through a small public web app, and
sends WhatsApp alerts when new jobs match a saved subscription. It is deployed at
`jobhubs.aavartlabs.com` via a Cloudflare Tunnel.

**This repo contains two generations of the project. Only one is live.**

1. **`poc/` — the current, live system.** A minimal Python pipeline (scraper → SQLite →
   Flask+TS web app → WhatsApp alerts), built 2026-09-16/17 as a 3-day pivot. This is what
   actually runs in production and what most work in this repo should target.
2. **`apps/` — the original, now-retired stack.** Spring Boot 3.3 + Next.js 16 +
   Postgres/pgvector + Ollama. It was scrapped as the active runtime surface because it was
   heavier than the goal and partially broken in production, but its source is left
   untouched in git history — see [Retired stack](#retired-stack-apps) below. Nothing in
   `apps/` is deployed anymore.

When in doubt, check which of these two a task actually concerns before assuming file
paths, commands, or architecture — they do not share code, dependencies, or deployment
targets. Full pivot rationale, "as-built vs. as-planned" corrections, and verification
steps live in `poc/PLAN.md`; day-to-day architecture and quick start live in `poc/README.md`.

## Live Architecture (`poc/`)

```
pi05: scraper/ + warehouse.db                 pi09: jobhub_poc/  (Docker container "jobhub-web")
  EverJobs (prebuilt Node dist)                  loader/   delta -> jobhub.db (serving), purge
  ingest.py: full sweep -> warehouse.db          webapp/   Flask JSON API + TS frontend
  export.py: gzip delta ------------------------> alerts/   matcher + notifier, account-owned
                                                 (pi09 orchestrates: ssh pi05 ingest+export,
                                                  scp the delta, load, purge, alert)

https://jobhubs.aavartlabs.com --(Cloudflare Tunnel, fixed target jobhub-web:3000)--> pi09
                                                                    |
                                                     pi09: jobhub-whatsapp container
                                                       (baileys WhatsApp Web session)
```

**Two data tiers (Stage 2, 2026-09-23).** All tunables live in `poc/config/pipeline.ini`
(read by `jobhub_poc/pipeline_config.py`, stdlib-only because pi05 imports it; env override
`JOBHUB_PIPELINE_<SECTION>_<KEY>`; unknown keys are errors). **Cutover status:** until T7 is
done, pi09's timer still runs the old `scripts/run_pipeline.sh` (filtered dump → `load_dump`);
the new path is `scripts/run_pipeline_warehouse.sh`, and the old script stays as rollback.

- **Warehouse (pi05, `~/jobhub-poc/scraper/data/warehouse.db`)**: `scraper/ingest.py` upserts
  the *whole* EverJobs sweep, unfiltered — same EverJobs id or same fingerprint (normalised
  title + company + city) is one job. Jobs whose posted date (`jobhub_poc/dates.py`) is older
  than `[ingest] max_posted_age_days` are neither inserted nor touched. `content_hash` means
  `updated_at` moves only on real content changes; `last_seen_at` moves on every sighting.
  Purged by `last_seen_at` after `warehouse_retention_days`. pi05 runs only the stdlib files
  `jobhub_poc/{__init__,dates,pipeline_config}.py` + `config/pipeline.ini`, not the app.
- **Export → serving**: `scraper/export.py --since <watermark>` writes a gzip JSONL delta of
  warehouse rows whose title matches `[serving] search_terms` (and `locations` if set): full
  records for new/changed jobs, tiny `touch` records for jobs merely seen again. pi09's
  `loader/load_delta.py` applies it and the watermark (`sync_state` table) in one transaction.
  `dedupe_key` is the EverJobs id — the same key `load_dump` always used — so a cutover
  doesn't re-announce existing jobs. **But** the first sync after cutover still inserts
  thousands of newly-eligible jobs: run it once with `SUPPRESS_ALERTS=1`.
- **Serving purge**: `loader/purge.py` deletes jobs not seen for `serving_retention_days`,
  keyed on `last_seen_at` (not first_seen — live listings survive), deleting their
  `alerts_sent` rows first (FK). `EVER_JOBS_SITE_NAMES` / `SEARCH_TERMS` / `RESULTS_PER_TERM`
  in `scraper/.env` only matter to the old `dump_jobs.py` path.
- **EverJobs facts**: which site buckets are scraped is decided **server-side** by
  `DEFAULT_SITE_NAMES` in pi05's EverJobs systemd unit (currently
  `google,naukri,linkedin,indeed,glassdoor`), not by the client. `query`/`results` are **not
  honored** — every call returns the whole sweep (2026-09-23: 15,203 jobs, ~3 min;
  ingest peak RSS ~570 MB; ~11k distinct fresh jobs ≈ 129 MB warehouse).
- **Posted dates** (`datePosted`) are unreliable — ISO, bare dates, epoch seconds, "Sep 23,
  2026", years-stale values. Never key retention on them; `dates.normalize_posted` only feeds
  the age filter and (T8) the "posted within" filter, falling back to first_seen.
- **Web app (pi09, Docker container `jobhub-web`)**: `poc/jobhub_poc/webapp/` is a Flask
  app (blueprints: `auth`, `auth_proxy`, `routes_jobs`, `routes_alerts`, `routes_api`); it
  holds no identity of its own — see [Accounts](#accounts-poc-web-app). `GET /api/jobs`
  (`routes_api.py`) returns paginated/filterable/sortable JSON; `poc/jobhub_poc/webapp/frontend/`
  is a small esbuild-bundled TypeScript client (no framework) that renders it —
  `templates/jobs.html` is just a shell that loads the compiled `static/app.js` (plus
  `static/auth.js` for the auth pages). The `Dockerfile` is a two-stage build: Node only at
  build time, Python-only at runtime. **The compiled `static/app.js` / `static/auth.js` are
  also committed to git** and are what the non-Docker `make web` path serves — after editing
  `frontend/src/*.ts`, run `npm run build` there and commit the regenerated bundles too.
- **Alerts**: `poc/jobhub_poc/alerts/matcher.py` finds active `alert_subscriptions` whose
  title/location keyword substrings match newly-inserted jobs (only ids returned by
  `load_dump()` as genuinely new are considered — not a timestamp-window heuristic).
  `notifier.py` sends via a pluggable `Notifier` (`get_notifier(backend, conn)`):
  `ConsoleNotifier` (stdout + `alerts_sent` row) or `WhatsAppNotifier` (HTTP POST to the
  `whatsapp-sender` gateway). Sends are idempotent — `alerts_sent` has a
  `UNIQUE(subscription_id, job_id)` constraint, so a re-run never double-fires.
  `NOTIFIER_BACKEND` env var switches backends with no code change; production currently
  runs `whatsapp`.
- **WhatsApp gateway (`poc/whatsapp-sender/`)**: a separate, hand-rolled Node service (no
  framework) holding a `baileys` (pinned `6.7.24`, not `7.0.0-rc*`) WhatsApp Web session.
  Exposes `GET /health` and `POST /send` (header `x-api-key`). Requires a one-time,
  un-scriptable QR-code pairing with a real phone (see `poc/whatsapp-sender/README.md`) —
  never pair it with a personal/business number, and never run two deployments against the
  same number (a second login silently kicks the first).
- **Cloudflare Tunnel routing is fixed and not editable from this repo**: the tunnel's
  ingress config targets `http://jobhub-web:3000` on the `jobhub` Docker network, set
  remotely in Cloudflare's dashboard. The only way to change what's publicly served is to
  make a container literally named `jobhub-web` on that network listen on port 3000 — which
  is why `poc/docker-compose.yml` hardcodes `container_name: jobhub-web` and why the
  compose file force-overrides `WEB_PORT: "3000"` even though the shared `.env`'s
  `WEB_PORT=8100` is the host-facing convention (Docker's embedded DNS re-resolves the name
  live, so swapping containers causes no tunnel downtime).

## Build, Run & Test Commands (`poc/`)

```bash
cd poc
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                       # edit as needed
.venv/bin/pytest -v                        # or: make test  (75 tests as of last count)

cd scraper
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pytest -v                        # separate venv/deps from poc/ (warehouse, export, dump tests)

cd ../whatsapp-sender
npm install && npm test                    # pure-logic tests only, no live WhatsApp needed

cd ../auth-service
npm install && npm test                    # mocked Resend + a local stub for whatsapp-sender

cd ../jobhub_poc/webapp/frontend
npm install && npm test                    # pure-logic TS helpers only (node --test, no DOM)
npm run build                              # typecheck + esbuild -> ../static/{app,auth}.js
```

Single test: `.venv/bin/pytest tests/test_matcher.py -v` or
`.venv/bin/pytest tests/test_matcher.py::test_name -v` (pytest's `testpaths = tests`);
for the Node packages, `node --test test/<name>.test.js` from that package's directory.

Run against the bundled real fixture without a live scraper:
```bash
cd poc
.venv/bin/python scripts/seed_demo_data.py     # loads fixtures/sample_everjobs_response_real.json
.venv/bin/python -m jobhub_poc.webapp.app      # http://localhost:8100/jobs   (public, no login)
```

`poc/Makefile` shortcuts: `make venv`, `make test`, `make test-scraper`,
`make seed-demo-data`, `make web`, `make dump`, `make load DUMP=<path>`, `make purge`,
`make alerts`, `make pipeline`.

**No CI job runs any `poc/` test.** `.github/workflows/ci.yml` only builds `apps/web`
(`npm run build`) and tests `apps/platform-api` (`mvn test`) — both parts of the retired
stack. `poc/`'s and `poc/scraper/`'s test suites are currently verified manually only.

## Deployment

- **pi05**: runs EverJobs (prebuilt Node server, systemd system service `jobhub-everjobs`,
  `Restart=always`, boot-enabled), the scraper venv (`dump_jobs.py` old path;
  `ingest.py`/`export.py` warehouse path) and the SQLite **warehouse** at
  `~/jobhub-poc/scraper/data/warehouse.db`. It never runs the web app. Deploy there = rsync of
  `poc/scraper/*.py`, `poc/jobhub_poc/{__init__,dates,pipeline_config}.py` and
  `poc/config/pipeline.ini` into `~/jobhub-poc/` (user `rudra`).
- **pi09**: runs the loader/purge/alerts CLIs directly via a Python venv against
  `~/jobhub-poc/data/jobhub.db`, plus Docker containers from `poc/docker-compose.yml`:
  `jobhub-web` (the Flask app), `jobhub-auth` (Better Auth), and `jobhub-whatsapp` (the
  gateway), all `restart: unless-stopped`. `jobhub-cloudflare-tunnel` also runs there but
  is not defined in this repo. `~/jobhub-poc` on pi09 is **not a git checkout** — deploys are
  an rsync of `poc/` (excluding `.env`, `data/`, `dumps/`, `.venv/`, `whatsapp-sender/auth_info/`,
  `auth-service/data/`) followed by `docker compose build && docker compose up -d`. The
  auth stack went live 2026-09-23; the Resend sender is `noreply@alerts.aavartlabs.com`
  (`alerts.aavartlabs.com` is the Resend-verified domain). Never runs EverJobs.
  **Also the orchestration host**, as of 2026-09-22 — `poc/scripts/run_pipeline.sh` runs locally on pi09 (`ssh pi05 ...` to scrape, direct `scp` back, then load/purge/alert
  with no further SSH hop) and is scheduled every 6 hours via a systemd **user** timer on
  pi09 itself (`~/.config/systemd/user/jobhub-pipeline.{service,timer}` — host config, not
  checked into this repo; `Linger=yes` so it runs unattended). Logs append to
  `~/jobhub-poc/pipeline.log` on pi09.
- **harita is no longer part of the runtime path.** It was originally the orchestration host
  because pi05↔pi09 SSH trust was unconfirmed; that trust now exists (pi09's own key is in
  pi05's `authorized_keys`), so the whole pipeline runs on always-on Pi hardware only —
  harita being a laptop/desktop that isn't reliably up 24/7 was exactly the risk this removed
  (see `tasks_all.md`'s T3/T7 entries). harita's old unit files are disabled, not deleted, on
  harita, as a rollback path.
- To change the pipeline cadence: edit `OnCalendar=` in that timer file on **pi09**, then
  `ssh pi09 "systemctl --user daemon-reload && systemctl --user restart jobhub-pipeline.timer"`.

## Key Environment Variables (`poc/.env.example`, separate from the root `.env.example`)

- `EVER_JOBS_API_URL` / `EVER_JOBS_API_KEY` — scraper target; `EVER_JOBS_SITE_NAMES` is
  informational only (see Scraper note above). `REQUEST_TIMEOUT_SECONDS` defaults to 600
- `SEARCH_TERMS` (comma-separated) / `RESULTS_PER_TERM` — **old dump path only**; the warehouse path uses `config/pipeline.ini [serving]`. Client-side filter/cap applied
  after the single EverJobs fetch, since server-side query params aren't honored
- `JOBHUB_SQLITE_PATH` — serving DB path (retention moved to `config/pipeline.ini [retention]`)
- `WEB_PORT` / `WEB_SECRET_KEY` — web app; note the Docker Compose deployment
  force-overrides `WEB_PORT` to `3000` regardless of what's in `.env` (see Cloudflare
  Tunnel note above) — don't trust `.env`'s `WEB_PORT` as what the container binds to
  internally
- `AUTH_SERVICE_URL` — where Flask reaches `poc/auth-service/` (compose overrides it to
  `http://auth-service:3200`)
- `WEB_ORIGIN` — this deployment's **public** origin. Compose passes it straight through to
  `auth-service` as both `BETTER_AUTH_URL` and `TRUSTED_ORIGINS` and refuses to start if
  it's unset, so it is the single place the public origin is configured. `poc/auth-service/.env`
  has its own set (`BETTER_AUTH_SECRET`, `RESEND_*`, `WHATSAPP_GATEWAY_*`) — read that
  file's comments, several of its defaults are correct only for non-Docker local dev
- `NOTIFIER_BACKEND` (`console` | `whatsapp`) / `WHATSAPP_GATEWAY_URL` /
  `WHATSAPP_GATEWAY_API_KEY` — alert delivery backend

## Accounts (`poc` web app)

Real self-service accounts, live since 2026-09-23. Identity lives in `poc/auth-service/`, a
second container (`jobhub-auth`) running Better Auth over its own `auth.db`; Flask
reverse-proxies `/auth/*` to it and issues no site-user session of its own. Signup is
email + password + mobile, with both the email (Resend) and the mobile (the existing
`whatsapp-sender` gateway) verified by OTP before the account can do anything. `/jobs` and
`/api/jobs` are public; `/alerts/*` requires a fully verified account and is scoped to
`alert_subscriptions.owner_auth_user_id`.

**Cloudflare Turnstile** gates signup, login, every OTP send, the alert form and the admin
login. Fetch-driven pages send a per-request token as `X-Turnstile-Token`; `auth_proxy.py`'s
`_TURNSTILE_ACTIONS` maps each protected Better Auth path to its action, and
`webapp/turnstile.py` checks success + action + hostname and fails closed. Adding a new
Better Auth endpoint that sends a message or checks a password means adding it there.

**Admin console (`/admin`)** is separate from site users: an `app_users` row in `jobhub.db`,
Flask's own session cookie (`jobhub_admin`), CSRF tokens on every POST, and a per-IP +
per-username lockout (`admin_login_attempts`). It edits users through auth-service's
`/internal/admin/*` API (`auth-service/src/admin.js`, key `AUTH_ADMIN_API_KEY`), which lives
outside `/auth/*` so the public proxy can never reach it. See `docs/rbac.md` and `poc/auth-service/README.md`.

## Retired stack (`apps/`)

Left in git history, untouched, not deployed, not extended. Kept here only for context if
someone resumes work on it.

```
Next.js 16 web portal  →  Spring Boot 3.3 platform-api  →  PostgreSQL 16 + pgvector
                                    ↓
                          Ollama (self-hosted LLM, called directly over HTTP)
                                    ↑
                          EverJobs (external NestJS scraper service, not in this repo)
```

- **No agent-runtime service, no Flowable.** `apps/agent-runtime` does not exist despite
  the root `Makefile`'s `run-agent` target and `AGENTS.md` referencing it. `workflow/dmn`
  and `workflow/processes` under `apps/platform-api/src/main/resources` are placeholder
  `README.txt` files only; Flowable was never a Maven dependency. Enrichment was a plain
  synchronous service call, not a BPMN process — `JobEnrichmentAgent` just recorded a
  `confidence` field from the model's JSON response.
- **Enrichment** was one Java service (`apps/platform-api/.../service/JobEnrichmentAgent.java`)
  calling Ollama's `/api/generate` over REST, no retry/guardrail layer.
- **Ingestion** pulled from EverJobs via `EverJobsClient` (`EVER_JOBS_API_URL`, header
  `x-api-key`); `ever-jobs-docker/` here was only a deploy `Dockerfile`/`package.json` for a
  prebuilt `dist/` of that separate project, never its source.
- **Flyway migrations were inert**: `spring.flyway.enabled: false`, schema managed by
  Hibernate `ddl-auto: update`. `V1__foundation.sql`/`V2__seed_rbac.sql` under `db/migration/`
  were never executed and were stale relative to the real schema.
- **Auth**: Spring Security + a self-issued HS256 JWT (Nimbus, not an external IdP). RBAC
  seed data came from `DemoDataSeeder` (idempotent via `tenantRepository.count() > 0`).
- **Tenant isolation**: shared schema + `tenant_id` column, app-level filtering only, no RLS.

If resuming this stack: `docker compose up --build` from repo root (web on :3001, API on
:8080, Postgres on :5432); `cd apps/platform-api && mvn test` (H2, not Postgres);
`bash scripts/smoke-test.sh` for a live-API smoke check. Demo accounts were
`{seeker,fresher,professional,recruiter,employer,admin}@jobhub.local` / `password`.

## Important Boundaries

- `poc/README.md` and `poc/PLAN.md` are the authoritative docs for the live system —
  `PLAN.md` also records where the original design assumptions were wrong (EverJobs' query
  params, the shape of `location`, source `datePosted` reliability) and is worth reading
  before changing loader/scraper logic.
- `artifacts/` holds the *original* design-authority docs (LLD v1.0, an E2E PDF, an earlier
  zip scaffold) for a much larger target architecture (Flowable BPMN/DMN, a Python
  agent-runtime on the OpenAI Agents SDK, Kafka/OpenSearch, a ~22-agent catalog) that was
  never built and is now further from reality than ever — historical/aspirational only.
- `AGENTS.md` and root `README.md` still describe the retired `apps/` stack, not the `poc/`
  pivot — prefer this file and the code in `poc/` when they conflict.
- `tasks_all.md` / `tasks_sanjay.md` are task boards for the original stack, not the `poc/`
  pivot.
- `memory/` holds session memory files for continuity across Claude sessions.
- `docs/data-flow.md`, `docs/rbac.md`, `docs/runbook.md` describe the retired `apps/` stack
  in more depth than this file.
