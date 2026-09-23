# JobHubNG POC pipeline

Minimal scraper -> SQLite -> web app -> alerts pipeline, replacing the Spring
Boot/Next.js/Postgres stack under `apps/` for a 3-day POC. See the repo root
`CLAUDE.md` for how this relates to (and diverges from) the original design,
and [`PLAN.md`](./PLAN.md) for the full design rationale behind this pivot --
why the old stack was scrapped, the decisions made, and what's still
stretch/not done before the Saturday demo.

## Architecture

```
pi05: scraper/            pi09: jobhub_poc/  (Docker container "jobhub-web")
  EverJobs (Node,           loader/    JSON dump -> SQLite (dedup, purge)
   prebuilt dist)           webapp/    Flask JSON API + TS frontend, public
  dump_jobs.py -----json--> alerts/    registration + matcher + notifier, account-owned
     (pi09 pulls directly, no relay host)

https://jobhubs.aavartlabs.com --(Cloudflare Tunnel, fixed target jobhub-web:3000)--> pi09
```

- **Scraper (pi05)**: `scraper/` runs independently, its own venv. EverJobs'
  query/results params are NOT honored server-side -- a site bucket (e.g.
  `google`) returns every job it has for ~1500+ registered companies
  regardless of query, in 2-3 minutes. `dump_jobs.py` therefore fetches once
  and filters/caps client-side per `SEARCH_TERMS`.
- **Loader/web/alerts (pi09)**: `jobhub_poc/`, one venv (loader/alerts CLIs
  run directly on the host) + one Docker container (`jobhub-web`, the Flask
  app). Freshness/purge is keyed solely on `first_seen_at` (our own
  discovery timestamp) -- real EverJobs data has posted-dates ranging from
  same-day to multiple years stale, so the source's own date can't drive
  purging.
- **Web frontend**: `webapp/routes_api.py` exposes `GET /api/jobs`
  (title/location filter, freshness/title sort) as JSON. `webapp/frontend/`
  is a small TypeScript client (no framework, built with esbuild) that
  fetches from it and renders the table -- `webapp/templates/jobs.html` is
  just a shell (filter form + empty `<tbody>`) that loads the compiled
  `static/app.js`. Both the JSON API and the page shell are **public** --
  browsing jobs needs no account. Only `/alerts/*` is gated.
- **Production**: `jobhubs.aavartlabs.com` (Cloudflare Tunnel, already
  running on pi09) has a **fixed** target of `http://jobhub-web:3000` on the
  `jobhub` Docker network -- set remotely in Cloudflare's dashboard, not
  editable from here. The `web` service in `docker-compose.yml` is built and
  run as a container literally named `jobhub-web` on that network for
  exactly that reason; swapping images/rebuilding is how you deploy, not by
  touching the tunnel. This replaced the old Next.js `jobhub-web` container
  (and the `postgres`/`platform-api`/`agent-runtime` containers, all
  retired) in place, with no tunnel downtime -- Docker's embedded DNS
  re-resolves `jobhub-web` to whatever container currently holds that name.
- **Accounts (pi09)**: `auth-service/`, a second small Node container
  (`jobhub-auth`) running Better Auth with its own SQLite file (`auth.db`,
  separate from `jobhub.db`). Flask reverse-proxies `/auth/*` to it over the
  internal `jobhub` network -- it publishes no host port, since the
  Cloudflare Tunnel's ingress is fixed to `jobhub-web` and Flask is the only
  public entrypoint. Self-service signup: email + password + mobile, with the
  email verified by a Resend OTP and the mobile by an OTP through the same
  `whatsapp-sender` gateway the alerts use. Alert subscriptions are owned per
  account (`alert_subscriptions.owner_auth_user_id`). See
  `auth-service/README.md`.
- **Alerts**: real registration + matching logic ships now; only a
  `ConsoleNotifier` (stdout + `alerts_sent` table) backs it for the POC. A
  real WhatsApp notifier is a one-line `NOTIFIER_BACKEND` swap once someone
  manually QR-pairs a dedicated number with OpenWA/whatsapp-gateway/baileys
  -- see `jobhub_poc/alerts/notifier.py`.

## Quick start (local)

```bash
cd poc
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # edit as needed
.venv/bin/pytest -v

cd scraper
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pytest -v
```

To exercise the web app against the bundled real fixture without needing a
live scraper:

```bash
cd poc
.venv/bin/python scripts/seed_demo_data.py     # loads fixtures/sample_everjobs_response_real.json
.venv/bin/python -m jobhub_poc.webapp.app      # http://localhost:8100/jobs
```

`/jobs` and `/api/jobs` are public, so that's all you need to browse. `/alerts/*`
needs a verified account, which needs `auth-service/` running alongside -- and a
full registration needs real Resend + WhatsApp credentials, so it can't be
completed on a bare local checkout. See `docs/runbook.md` for what is and isn't
possible locally.

## Deployment

- pi05 runs `scraper/` only (Node, for the prebuilt EverJobs server, plus a
  Python venv for `dump_jobs.py`). Never runs the web app or SQLite.
- pi09 runs the loader/purge/alerts CLIs directly (Python venv) against
  `~/jobhub-poc/data/jobhub.db`, and the web app as a Docker container
  (`docker compose up -d --build` from `~/jobhub-poc/`, using this repo's
  `Dockerfile`/`docker-compose.yml` -- multi-stage build, Node only at build
  time for the TS bundle, Python-only at runtime). The container bind-mounts
  the same `data/` directory the CLIs write to. Never runs EverJobs.
- `scripts/run_pipeline.sh` orchestrates the scrape/load/purge/alert steps
  **on pi09 itself** (as of 2026-09-22) -- `ssh pi05` to scrape, a direct
  `scp` back (pi05<->pi09 SSH trust now exists, pi09's own key is in pi05's
  `authorized_keys`), then load/purge/alert locally, no further SSH hop.
  No relay host is involved anymore. It does not touch the web container.
- **Scheduling**: `run_pipeline.sh` runs automatically every 6 hours via a
  systemd user timer **on pi09** (`~/.config/systemd/user/jobhub-pipeline.{service,timer}`
  -- not part of this repo, since it's host config, not application code;
  `Linger=yes` so it runs unattended). Logs go to `~/jobhub-poc/pipeline.log`
  on pi09. EverJobs on pi05 runs as a systemd system service
  (`/etc/systemd/system/jobhub-everjobs.service`, `Restart=always`, enabled
  on boot). `jobhub-web` and `jobhub-whatsapp` on pi09 already auto-restart
  via Docker's `restart: unless-stopped`. **The whole pipeline now runs
  entirely on always-on Raspberry Pi hardware** -- a third host (harita, a
  laptop/desktop that isn't reliably up 24/7) was originally in the loop
  only because pi05<->pi09 trust was unconfirmed at design time; harita's
  old timer is disabled (not deleted) there as a rollback path.

## Job alerts (v2)

A signed-in, verified user creates alerts at `/alerts/register`: comma-separated job
titles, locations, companies and description keywords (OR within a field, AND across
fields; whole words; Bangalore = Bengaluru etc.), an optional work mode, and whether to
receive them by email, WhatsApp or both — always to the account's own verified contacts.
Each pipeline run sends **one digest per alert per channel** (up to 10 jobs + "N more",
linking back to JobHub). Dry-run the next run's digests without sending anything:

    NOTIFIER_BACKEND=console .venv/bin/python -m jobhub_poc.alerts.run_alerts --recent-minutes 1440

Email digests need `RESEND_API_KEY` and `RESEND_FROM_EMAIL` (a Resend-verified domain) in
`poc/.env`; contacts come from auth-service via `AUTH_SERVICE_URL` + `AUTH_ADMIN_API_KEY`.

## Bot protection and the admin console

**Cloudflare Turnstile** guards every request a bot could abuse: signup, login, every
email and WhatsApp code send (including resends), the alert subscription form, and the
admin login. The browser gets a fresh single-use token per request (`frontend/src/turnstile.ts`
for the fetch-driven auth pages, an implicit widget on the server-rendered forms) and
Flask verifies it with Cloudflare's siteverify (`webapp/turnstile.py`) before anything
reaches auth-service or the database, requiring `success`, the expected action, and a
hostname in `TURNSTILE_HOSTNAMES` (default: `WEB_ORIGIN`'s host). It fails closed. Config:
`TURNSTILE_SITEKEY`, `CF_TURNSTILE_SECRET`; see `.env.example` for Cloudflare's test keys
for local dev (`TURNSTILE_ALLOW_TEST_KEYS=1`, never in production).

**Admin console** at `/admin`: sign in as an `app_users` row (create or rotate one with
`scripts/set_admin_password.py <username>`, which also clears that username's lockout), then
list every registered user with their verification state, sessions and alert counts; edit
name/email/mobile and the two verified flags; sign a user out everywhere; or delete them
(with their alert subscriptions and history). User records are changed through
auth-service's internal `/internal/admin/*` API, keyed by `AUTH_ADMIN_API_KEY` and not
reachable through the public `/auth/*` proxy. Login brute force: Turnstile, then a lockout
per IP and per username (`ADMIN_MAX_FAILURES`, default 5 -> 15 min, doubling, capped at 24h),
every attempt logged to `docker logs jobhub-web`.



- An evergreen listing that keeps reappearing every scrape is purged 15 days
  after we *first* saw it, not 15 days after it stops appearing --
  `first_seen_at` is never updated on re-load, only `last_seen_at` is. Now
  that the pipeline runs on a real schedule (see above), this is a live
  consideration, not just a hypothetical: a job that's been open the whole
  time still drops off 15 days after we first noticed it.
- "Location" filtering in the web UI is client-side over whatever `location`
  field a scraped job happens to have -- EverJobs itself can't be asked for
  jobs in a specific place.
- Accounts are usable only once *both* the email and mobile OTP are
  verified, and there is no password-reset or "claim my existing alert" flow
  yet. The 4 alert subscriptions that predate accounts keep running unowned
  (`owner_auth_user_id IS NULL`) -- they still fire, but nobody can see or
  manage them through the UI.
