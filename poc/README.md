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
   prebuilt dist)           webapp/    Flask JSON API + TS frontend, login-gated
  dump_jobs.py -----json--> alerts/    registration + matcher + notifier
                (via harita)           (console notifier for now)

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
  `static/app.js`. Both the JSON API and the page shell are behind the same
  login gate (`app_users`/session) as the rest of the app.
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
.venv/bin/python scripts/seed_demo_user.py     # creates WEB_ADMIN_USERNAME/PASSWORD login
.venv/bin/python scripts/seed_demo_data.py     # loads fixtures/sample_everjobs_response_real.json
.venv/bin/python -m jobhub_poc.webapp.app      # http://localhost:8100/jobs
```

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
  from **harita** (or any host with the `pi05`/`pi09` SSH aliases
  configured), relaying the JSON dump through harita rather than assuming
  pi05<->pi09 trust. It does not touch the web container.

## Known, deliberate simplifications

- An evergreen listing that keeps reappearing every scrape is purged 15 days
  after we *first* saw it, not 15 days after it stops appearing --
  `first_seen_at` is never updated on re-load, only `last_seen_at` is. Fine
  for a manually-triggered pipeline; revisit if this runs on a real cron.
- "Location" filtering in the web UI is client-side over whatever `location`
  field a scraped job happens to have -- EverJobs itself can't be asked for
  jobs in a specific place.
- One shared demo login (`WEB_ADMIN_USERNAME`/`WEB_ADMIN_PASSWORD`), not
  per-user accounts.
