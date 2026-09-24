# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

JobHubNG is a job intelligence pipeline: it scrapes jobs from an external service
(EverJobs), stores them in SQLite, serves them through a small public web app, and
sends Telegram (and email) alerts when new jobs match a saved subscription. It is deployed at
`jobshub.aavartlabs.com` via a Cloudflare Tunnel, as **JobsHub** (renamed 2026-09-24 from
"JobHub POC" on `jobhubs.aavartlabs.com`; that old hostname is still routed by the tunnel
and 301/308-redirected by the app to the same path on the new one, via `LEGACY_HOSTS`).

**This repo contains two generations of the project. Only one is live.**

1. **`poc/` — the current, live system.** A minimal Python pipeline (scraper → SQLite →
   Flask+TS web app → Telegram/email alerts), built 2026-09-16/17 as a 3-day pivot. This is what
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

https://jobshub.aavartlabs.com --(Cloudflare Tunnel, fixed target jobhub-web:3000)--> pi09
                                                                    |
                  pi09 containers: jobhub-auth (Better Auth), jobhub-telegram (bot gateway;
                  Telegram's webhook arrives via web's /telegram/webhook), jobhub-whatsapp
                  (baileys session, admin fallback only)
```

**Two data tiers (Stage 2, 2026-09-23).** All tunables live in `poc/config/pipeline.ini`
(read by `jobhub_poc/pipeline_config.py`, stdlib-only because pi05 imports it; env override
`JOBHUB_PIPELINE_<SECTION>_<KEY>`; unknown keys are errors). **Cutover done 2026-09-23 ~19:35 IST**: pi09's timer runs `scripts/run_pipeline_warehouse.sh`;
the old `scripts/run_pipeline.sh` (filtered dump → `load_dump`) is kept only as rollback (switch
`ExecStart` back in `~/.config/systemd/user/jobhub-pipeline.service`). The old dump archives
(16–23 Sep, 31 files, identical on both Pis) were archived on 2026-09-24 to MinIO
`jobshub-data/archive/dumps/jobhub-dumps-20260916-20260923.tar.gz` (42.6 MB, sha256 in its
metadata, verified by re-download) and deleted from both Pis; the empty `dumps/` folders
remain only for the rollback path.

- **Warehouse (pi05, `~/jobhub-poc/scraper/data/warehouse.db`)**: `scraper/ingest.py` upserts
  the *whole* EverJobs sweep, unfiltered — same EverJobs id or same fingerprint (normalised
  title + company + city) is one job. Jobs whose posted date (`jobhub_poc/dates.py`) is older
  than `[ingest] max_posted_age_days` are neither inserted nor touched. `content_hash` means
  `updated_at` moves only on real content changes; `last_seen_at` moves on every sighting.
  **History is kept (2026-09-24):** before a content change overwrites a job, the previous
  version goes to `job_versions` (zlib-compressed raw JSON + the span it was current), and
  retention *moves* jobs unseen for `warehouse_retention_days` into `jobs_archive` instead of
  deleting them (~1,200 changed jobs/day → a few MB/day compressed; pi05 has ~47 GB free). pi05 runs only the stdlib files
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
  app (blueprints: `auth`, `auth_proxy`, `routes_jobs`, `routes_alerts`, `routes_api`, `admin`); it
  holds no identity of its own — see [Accounts](#accounts-poc-web-app). **Pages are
  server-rendered Jinja + Tailwind CSS v4 (since 2026-09-24), phone-first** (unprefixed
  classes = phone, `sm:`/`lg:` add wider layouts). The jobs flow (`routes_jobs.py`): `/jobs`
  is hero search (`q` = title or company; old `title=` still accepted; location with a
  datalist; `work_mode` remote/onsite) + stats cards + the list (each row an
  `<a id="job-<id>" class="job-row">` with initials tile, real badges only: location,
  Remote, type, salary, posted, New — no invented ratings/experience); filters/sort/page
  are plain GET params so the URL is the list state. **On a PC (`lg`, ≥1024px) it's a split
  view**: the pane beside the list shows `?sel=<id>` or the first row (the default one never
  records a view); `app.ts` swaps it via `/jobs/<id>/panel` (HTML fragment) and
  `history.replaceState`s `sel` (not push, so Back leaves the list); ↑/↓ move. Below `lg`
  rows open the job page as before. Descriptions go through `webapp/job_text.py`
  (`format_description`: decode entities, drop any tags, escape, then add only
  paragraphs/bullets/headings/bold — never trusts source HTML). `/jobs/<id>` is one
  job (anyone sees the basics; description + Apply need a verified account; Back returns to
  `/jobs?<same params>#job-<id>`, or `history.back()` when the list is the referrer, so the
  same row comes back); `/jobs/<id>/apply` records `click_apply` then 302s to the employer
  (http/https only), opened in a new tab. Old `/jobs?job=<id>` links redirect. The list
  query, param whitelist and "posted" label live in `webapp/jobs_listing.py`, shared with
  `GET /api/jobs` (`routes_api.py`, JSON, kept for API callers). Styling:
  `frontend/src/styles.css` (theme tokens = the plum/magenta palette; `@layer base` styles
  bare elements, `@layer components` has `.btn`, `.btn-secondary`, `.btn-danger`, `.card`,
  `.table-card`, `.nav-link`, …) → `static/app.css`; Tailwind only emits classes it finds
  in `templates/` and `frontend/src/`, so a class built from string pieces won't exist.
  `frontend/src/*.ts` is now only small enhancements (`app.ts`) and the auth pages
  (`auth.ts`). The `Dockerfile` is a two-stage build: Node only at build time (it copies
  `templates/` into the build stage for Tailwind), Python-only at runtime. **The compiled
  `static/app.js`, `static/auth.js` and `static/app.css` are also committed to git** and are
  what the non-Docker `make web` path serves — after editing `frontend/src/*` *or any
  template's classes*, run `npm run build` there and commit the regenerated files too.
- **Alerts (v2, 2026-09-23)**: an alert is its owner's filters — JSON lists `titles`,
  `locations`, `companies`, `keywords` (OR within a list, AND across; whole-word, with
  location aliases like Bangalore/Bengaluru, `alerts/rules.py`) plus `work_mode` — and which
  of the owner's **own verified contacts** get it (`notify_email`/`notify_telegram`; was
  `notify_whatsapp` until 2026-09-24, `db._migrate_alerts_telegram` rebuilt the tables and
  kept WhatsApp rows in `alerts_sent` as history). No address is stored per alert:
  `alerts/contacts.py` reads email / Telegram chat id from auth-service's
  `/internal/admin/users` at send time (the host reaches it on
  `127.0.0.1:3200`, published loopback-only by compose). `run_alerts` groups new-job matches
  per alert and `alerts/delivery.py` sends **one digest per alert per channel per run**
  (`alerts/digest.py`, ≤10 jobs linking to `/jobs/<id>` + "N more") via
  `alerts/senders.py` (the Telegram gateway, or Resend email with `RESEND_FROM_EMAIL`).
  `alerts_sent` has `UNIQUE(subscription_id, job_id, channel)` and records SENT / FAILED /
  SKIPPED (unverified channel), so re-runs never resend; alerts of deleted users are
  deactivated. "New" means inserted into jobhub.db **and** first seen by the warehouse after
  the previous sync (`load_delta`), so bulk re-syncs never announce old jobs. Active alert
  titles/keywords are shipped to pi05 each run (`alerts/alert_terms.py`) and widen the
  export; a changed term set triggers a full warehouse re-scan. `NOTIFIER_BACKEND=console`
  prints digests instead of sending (dry run); `live` (or legacy `whatsapp`) sends.
- **Telegram gateway (`poc/telegram-gateway/`, container `jobhub-telegram`, since
  2026-09-24)**: the only holder of the bot token (@AavartJobsAlert_bot); no npm deps. Out:
  `POST /send` (`x-api-key` = `TELEGRAM_GATEWAY_API_KEY`; `410 blocked` if the user blocked
  the bot); host CLIs reach it on `127.0.0.1:3300`. In: Telegram posts to
  `https://<site>/telegram/webhook` (`webapp/telegram_webhook.py`, a passthrough) → gateway
  `POST /webhook`, which checks `TELEGRAM_WEBHOOK_SECRET` and re-registers the webhook on
  every boot — so `getUpdates` no longer works for this bot. **Extension point for anything
  users send the bot:** `src/router.js` normalises updates (command / text / inline-button
  callback `"<action>:<arg>"`), `src/handlers.js` registers what they do. Today `/start
  <token>` asks auth-service for the reply (a linking code); anything else gets help with
  the user's chat id.
- **WhatsApp gateway (`poc/whatsapp-sender/`)**: now only the admin-message fallback
  (`admin_notify.py`) — user alerts and signup moved to Telegram on 2026-09-24 because the
  baileys session kept desyncing (Bad MAC / "Waiting for this message", stream 503s). A
  separate, hand-rolled Node service (no
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
.venv/bin/pytest -v                        # or: make test  (288 tests on 2026-09-24)

cd scraper
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pytest -v                        # separate venv/deps from poc/ (warehouse, export, dump tests)

cd ../whatsapp-sender
npm install && npm test                    # pure-logic tests only, no live WhatsApp needed

cd ../auth-service
npm install && npm test                    # mocked Resend; Telegram linking against in-memory SQLite

cd ../telegram-gateway
npm test                                   # no deps; fake Bot API and fake auth-service

cd ../jobhub_poc/webapp/frontend
npm install && npm test                    # pure-logic TS helpers only (node --test, no DOM)
npm run build                              # typecheck + esbuild + Tailwind -> ../static/{app,auth}.js, app.css
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
`make alerts`, `make pipeline`. Note `make pipeline` (and `dump`/`load`) still drive the
**old** `scripts/run_pipeline.sh` rollback path, not the live warehouse path
(`scripts/run_pipeline_warehouse.sh`).

**No CI job runs any `poc/` test.** `.github/workflows/ci.yml` only builds `apps/web`
(`npm run build`) and tests `apps/platform-api` (`mvn test`) — both parts of the retired
stack. `poc/`'s and `poc/scraper/`'s test suites are currently verified manually only.

## Deployment

- **pi05**: runs EverJobs (prebuilt Node server, systemd system service `jobhub-everjobs`,
  `Restart=always`, boot-enabled), the scraper venv (`dump_jobs.py` old path;
  `ingest.py`/`export.py` warehouse path) and the SQLite **warehouse** at
  `~/jobhub-poc/scraper/data/warehouse.db`. It never runs the web app. Deploy there = rsync of
  `poc/scraper/*.py`, `poc/jobhub_poc/{__init__,dates,pipeline_config}.py` and
  `poc/config/pipeline.ini` into `~/jobhub-poc/` on pi05.
- **pi09**: runs the loader/purge/alerts CLIs directly via a Python venv against
  `~/jobhub-poc/data/jobhub.db`, plus Docker containers from `poc/docker-compose.yml`:
  `jobhub-web` (the Flask app), `jobhub-auth` (Better Auth), `jobhub-telegram` (the
  Telegram gateway), `jobhub-whatsapp` (admin fallback) and `jobhub-cloudflare-tunnel` (service
  `tunnel`; token from the file `~/jobhub-poc/secrets/cloudflare-tunnel.token` via
  `TUNNEL_TOKEN_FILE`, never env/args), all `restart: unless-stopped`. `~/jobhub-poc` on pi09 is **not a git checkout** — deploys are
  an rsync of `poc/` (excluding `.env`, `data/`, `dumps/`, `.venv/`, `whatsapp-sender/auth_info/`,
  `auth-service/data/`, `secrets/`) followed by `docker compose build && docker compose up -d`. The
  auth stack went live 2026-09-23; the Resend sender is `noreply@alerts.aavartlabs.com`
  (`alerts.aavartlabs.com` is the Resend-verified domain). Never runs EverJobs.
  **Also the orchestration host**, as of 2026-09-22 — `poc/scripts/run_pipeline_warehouse.sh` (since the
  2026-09-23 cutover; `run_pipeline.sh` before it) runs locally on pi09 (`ssh pi05 ...` to scrape, direct `scp` back, then load/purge/alert
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

## Backups (MinIO on pi06, since 2026-09-24)

- **What/when:** `jobshub-backup.timer` on pi09 (02:30 IST, user unit; templates in
  `poc/deploy/systemd/`) runs `poc/scripts/nightly_backup.sh`: `backup_to_minio.sh` for pi09's
  `data/jobhub.db` + `auth-service/data/auth.db`, then the same script on pi05 over SSH for
  `scraper/data/warehouse.db` (pi05's user has no systemd linger). Log: `~/jobhub-poc/backup.log`.
- **How:** SQLite online backup → `quick_check` → gzip → `mc cp` to
  `jobshub-data/backups/daily/<local date>/<host>/<db>.gz` with a `sha256` metadata attribute,
  then size re-check; Sundays also `weekly/`, the 1st also `monthly/`. Bucket lifecycle
  expires daily/weekly/monthly after 14/84/365 days. ~44 MB per night.
- **Access:** MinIO on pi06 (endpoint in each host's `~/.jobshub-minio.env`; plain HTTP on the LAN, **no client-side
  encryption** by Sanjay's choice). User `jobshub-backup` can get/put/list in
  `jobshub-data` only — no delete, no other buckets. Its keys are in `~/.jobshub-minio.env`
  (0600) on pi05/pi06/pi09 and reach `mc` only via `MC_HOST_jb`, never argv. `mc` is
  `~/bin/mc` on pi05/pi09.
- **Restore drill (weekly):** `jobshub-restore-drill.timer` on pi09 (Sundays 04:00 IST) runs
  `python -m jobhub_poc.ops.restore_drill`: for each DB it takes the newest daily backup
  (FAIL if > 2 days old — backups stopped), checks the upload sha256, decompresses, runs
  `PRAGMA integrity_check` and checks key tables aren't empty. Results in `backup.log`
  (`PASS/FAIL host/db [date] ...`); a failure also fails the unit
  (`systemctl --user status jobshub-restore-drill` on pi09).
- **Failure alerts:** the backup, restore-drill and cold-export units have
  `OnFailure=jobshub-alert-admin@%n.service`, which runs `jobhub_poc.ops.alert_admin`: one
  message with the unit and the tail of `backup.log`, to the admin only — never to site
  users. Admin messages (these and admin sign-in codes) go through `jobhub_poc/admin_notify.py`:
  Telegram (`TELEGRAM_BOT_TOKEN` + `ADMIN_TELEGRAM_CHAT_ID`, Bot API) first, then
  `ADMIN_ALERT_WHATSAPP` via the gateway as fallback, all in pi09's `.env`. Set up / check
  with `python -m jobhub_poc.ops.telegram_setup chats|test`. The Telegram sender never lets
  a `requests` error through, since the bot token is in the URL.
- **Cold history (monthly):** `jobshub-cold-export.timer` on pi09 (1st of the month, 03:30
  IST) runs `scraper/cold_export.py` on pi05 over SSH: `jobs_archive` rows archived and
  `job_versions` spans ended more than `[archive] cold_after_days` (90) ago are uploaded as
  gzip JSONL (version JSON decompressed) to `jobshub-data/archive/history/<date>/`, and only
  after the upload is verified are they deleted from the warehouse (then `VACUUM`).
- **Restore:** on any host with the env file:
  `set -a; . ~/.jobshub-minio.env; set +a; export MC_HOST_jb="http://${MINIO_ACCESS_KEY}:${MINIO_SECRET_KEY}@${MINIO_ENDPOINT#*://}"`,
  then `~/bin/mc ls jb/jobshub-data/backups/daily/` → `~/bin/mc cp jb/jobshub-data/backups/daily/<date>/<host>/<db>.gz .`
  → `gunzip` → check `PRAGMA integrity_check` → stop the container/pipeline that uses it and
  swap the file in.

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
  has its own set (`BETTER_AUTH_SECRET`, `RESEND_*`) — read that
  file's comments, several of its defaults are correct only for non-Docker local dev
- `NOTIFIER_BACKEND` (`console` | `live`; `whatsapp` is a legacy alias for `live`) — alert
  delivery backend
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `TELEGRAM_GATEWAY_URL` (host:
  `http://127.0.0.1:3300`; compose overrides it for web), `TELEGRAM_GATEWAY_API_KEY`,
  `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_INTERNAL_API_KEY` — all in `poc/.env`; compose hands
  each container only the ones it needs (the gateway has no `env_file`)
- `WHATSAPP_GATEWAY_URL` / `WHATSAPP_GATEWAY_API_KEY` / `ADMIN_ALERT_WHATSAPP` — admin
  fallback only

## Accounts (`poc` web app)

Real self-service accounts, live since 2026-09-23. Identity lives in `poc/auth-service/`, a
second container (`jobhub-auth`) running Better Auth over its own `auth.db`; Flask
reverse-proxies `/auth/*` to it and issues no site-user session of its own. Signup is
email + password, then the email verified by a Resend OTP before the account can do
anything. **Telegram is optional** (Sanjay, 2026-09-24): linking it on /verify (any time)
only unlocks Telegram alerts — the alert form disables that option and the server refuses
`notify_telegram` without `telegramVerified`. Linking
(`auth-service/src/telegram.js`): signed in, `POST /auth/telegram/link` gives a one-time
`t.me/<bot>?start=<token>`; pressing Start makes the gateway call auth-service's
`/internal/telegram/start` (key `TELEGRAM_INTERNAL_API_KEY`), which replies with a 6-digit
code bound to that user and chat; `POST /auth/telegram/verify {code}` sets
`telegramChatId`/`telegramUsername`/`telegramVerified` (Better Auth plugin fields, `input:
false`). The code must come back through the site session, so a forwarded link can't
attach someone else's Telegram. One chat links to one account: a chat already on another
account gets no code at `/start`, only that account's masked email ("sign in with that
account instead"); verify re-checks, and auth-service's startup builds a partial unique
index `user_telegram_chat_unique` (skipped with an error log if duplicates already exist). `/jobs` and
`/api/jobs` are public; `/alerts/*` and `/saved` require a verified email and are scoped to
the owner. **Saved jobs** (`saved_jobs`, keyed by owner + job `dedupe_key` with a title/company
snapshot, so a purged job still shows "No longer listed"): `POST /jobs/<id>/save|unsave`
(plain forms; JSON when `Accept: application/json`, which app.ts uses to toggle in place),
`/saved`, `POST /saved/remove`. **Share** on the job details: the phone's share sheet, else
copy `WEB_ORIGIN/jobs/<id>` (public page).

**Cloudflare Turnstile** gates signup, login, every OTP send, the alert form and the admin
login. Fetch-driven pages send a per-request token as `X-Turnstile-Token`; `auth_proxy.py`'s
`_TURNSTILE_ACTIONS` maps each protected Better Auth path to its action, and
`webapp/turnstile.py` checks success + action + hostname and fails closed. Adding a new
Better Auth endpoint that sends a message or checks a password means adding it there.

**Resume features (phase 1 of 4, 2026-09-24; plan in memory `jobhubng_career_features`).**
`/profile`: upload PDF/DOCX (≤5 MB, identified by magic bytes, consent checkbox) →
`resume_text.extract_text` → encrypted row in `resumes` (Fernet, `crypto.py`, key
`RESUME_ENCRYPTION_KEY` in `.env`; unset = feature off) → `ai_tasks` queue → container
`jobhub-ai` (`ai/worker.py`) calls the **local LLM** (Ollama, `OLLAMA_URL`/`OLLAMA_MODEL`,
gemma4:e2b on harita's GPU — resumes never leave the LAN) → `resume_parse.normalise` keeps it
honest (skills must appear in the text; bullets not found verbatim are flagged ⚠) → the user
reviews/edits it, and that edited version is the source of truth for later matching and
tailoring. harita may be off: tasks wait, the UI says so. Delete button and admin deletion
purge it (`routes_profile.purge_user_resume_data`).

**Match score (phase 2).** When a user with a checked resume opens a job (priority 5) or sees
it in a list (priority 1), an `extract_job` task has the LLM read the posting into
`job_requirements` (cached per dedupe_key; `job_requirements.normalise` keeps only skills that
appear in the posting text and years it actually states). `matching.match` then scores
**deterministically, no LLM**: required skills 45, preferred 15, experience 20, seniority 10,
location 10 → Strong ≥75 / Good ≥55 / Stretch ≥40 / Not a fit, with reasons. Caps: >60% of
must-haves missing → at most Stretch; <3 requirements found → at most Good, marked rough.
Shown as `_match.html` in the pane/page (app.js polls `/jobs/<id>/match` while it's 202) and a
badge on list rows.

**Admin console (`/admin`)** is separate from site users: an `app_users` row in `jobhub.db`,
Flask's own session cookie (`jobhub_admin`), CSRF tokens on every POST, and a per-IP +
per-username lockout (`admin_login_attempts`). Sign-in is two-step: the password only starts a
pending sign-in; a 6-digit code (5 min, 5 tries, `admin_codes.py` / `admin_login_codes`)
goes to the admin via `admin_notify.py` (Telegram, else WhatsApp). If it can't be sent, a shell on pi09 gets one with
`scripts/admin_login_code.py <username>`; a forgotten password or a lockout is reset with
`scripts/set_admin_password.py <username>`. It edits users through auth-service's
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
- `docs/data-flow.md`, `docs/rbac.md`, `docs/runbook.md` lead with the live `poc/` system
  and keep the retired `apps/` design further down, for context only.
