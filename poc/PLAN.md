# JobHubNG POC Pivot — Scraper → SQLite → Simple Webapp → Stubbed Alerts

> **Status (2026-09-16):** Implemented and verified live end-to-end — scraper deployed on
> pi05, `jobhub_poc` (loader/webapp/alerts) deployed on pi09, 43 tests green, full pipeline
> run confirmed against real EverJobs data. See `poc/README.md` for current quick-start and
> deployment notes; this document is the original design rationale, kept for context on
> *why* things are shaped this way.

## Context

The current Spring Boot 3.3 + Next.js 16 + Postgres/pgvector stack (`apps/platform-api`,
`apps/web`) is not meeting the need. On top of being architecturally heavier than the goal
("this is not UI/UX... a foothold"), the live pi09 deployment is currently partially broken
(`jobhub-platform-api` container crash-looping on a Hibernate dialect bug). Rather than debug
that stack, the decision is to scrap it as the active runtime surface (old code stays in git
history, untouched) and build a small, POC-grade pipeline for a demo by **Saturday 2026-09-19**
(today is Wed 2026-09-16 — a 3-day build window).

Four foundational decisions were made explicitly (all "recommended" options, confirmed via
AskUserQuestion):
1. **Clean rewrite** — new, separate, minimal codebase; `apps/platform-api`/`apps/web` are
   left alone, not deleted, not extended.
2. **Python** for every new piece (loader, SQLite, web app, alert logic) — pi05 (the scrape
   host) already has Python 3.13 and no Docker/Node, so this avoids extra runtime installs
   there for everything except EverJobs itself (which is a fixed, already-built Node artifact).
3. **WhatsApp sending is stubbed for Saturday** — real alert *logic* (registration, matching,
   idempotent send-log) is built for real, behind a `Notifier` interface; only a console/log
   notifier ships this week. Real WhatsApp (via `rmyndharis/OpenWA`, `kortix-ai/whatsapp-gateway`,
   or raw `baileys`) is an explicit fast-follow — it needs a dedicated phone number and a manual
   QR-code pairing step that can't be scripted, and isn't worth risking the Saturday deadline on.
4. **Sudo on pi05**: the user is provisioning `~/.env.sudo.password` themselves; nothing in this
   plan asks for or handles that password directly.

**Hosting split** (per explicit instruction): the web app + SQLite + loader + alerts run on
**pi09** (192.168.2.174, user `sanjayu`, Docker already installed, currently hosts the old
broken stack — leave it running, use different ports/network). **EverJobs itself runs on pi05**
(192.168.2.116, user `rudra`, a personal Debian 13 aarch64 Pi with Python but no Docker/Node),
never on pi09. Both are reachable passwordlessly over SSH from the current host, **harita**
(confirmed working). Orchestration scripts run *from* harita, since pi05↔pi09 direct trust is
unconfirmed. Everything is env-configured (hosts, ports, keys, paths) — nothing hardcoded, since
this eventually moves to AWS or another cloud provider.

**Biggest known risk (at design time)**: the prebuilt EverJobs server bundle (only artifact
available — its real NestJS source isn't in this repo or on either host) depends on
**Playwright/Chromium** for at least some of its 5 sites (LinkedIn/Indeed/ZipRecruiter/Glassdoor/
Google), confirmed via string search in the 16MB bundle. Whether headless Chromium scraping
actually works from a residential homelab IP on an ARM64 Pi that's never run a browser
automation stack before was genuinely unproven at design time.

> **Resolved during implementation**: live scraping worked, but not the way assumed. The
> `query`/`results` request params are **not honored server-side** — a "site bucket" like
> `google` scrapes ~1,500-2,000 companies' career pages and returns *everything* regardless
> of query (confirmed live: 15,000+ jobs, 79MB, ~2.5 minutes for one call). The scraper was
> adapted to fetch once per pipeline run and filter/cap client-side by `SEARCH_TERMS`,
> instead of one API call per term. Real data also confirmed `location` is a nested
> `{city,state,country}` object (not a flat string) and that source `datePosted` values
> ranged from 2021 to 2026 — validating the `first_seen_at`-only freshness/purge design
> below. See `poc/README.md` and `poc/scraper/dump_jobs.py`/`everjobs_client.py` for the
> as-built behavior.

## Repository layout (new — everything under `poc/`, root left untouched)

```
poc/
  README.md                    # architecture + quick start for this pivot
  .env.example                 # POC-specific env template (separate from root .env.example)
  requirements.txt             # flask, python-dotenv, pytest, requests-mock
  pytest.ini
  Makefile                     # dump / load / purge / alerts / web / pipeline / test targets

  jobhub_poc/                  # runs on pi09 — one venv, one package
    config.py                  # every env var, one place, no hardcoding
    db.py                      # get_connection(), init_db() applies schema.sql
    schema.sql
    loader/
      load_dump.py             # CLI: JSON dump -> upsert into jobs (dedup, first_seen_at)
      purge.py                 # CLI: delete jobs.first_seen_at older than PURGE_WINDOW_DAYS
    webapp/
      app.py                   # Flask app factory
      auth.py                  # login_required, password check vs app_users
      routes_jobs.py           # /jobs — filter by title/location, sort by freshness
      routes_alerts.py         # /alerts/register
      templates/ (base, login, jobs, alerts_register)
      static/style.css
    alerts/
      notifier.py              # Notifier ABC + ConsoleNotifier + get_notifier(name)
      matcher.py                # find_matches(conn, new_job_ids) -> [(subscription, job)]
      run_alerts.py             # CLI: match + notify + log to alerts_sent

  tests/                       # mirrors jobhub_poc/, pytest, TDD-first
  fixtures/sample_everjobs_response.json   # hand-authored, matches the CONFIRMED envelope
  scripts/
    seed_demo_user.py
    seed_demo_data.py
    run_pipeline.sh            # orchestration entrypoint, executed FROM harita

  scraper/                     # deployed separately to pi05 — its own venv/deps
    everjobs_client.py         # requests wrapper: search(query, results) -> list[dict]
    dump_jobs.py                # CLI: loop SEARCH_TERMS, write timestamped JSON to DUMP_DIR
    config.py
    tests/
```

Flask + Jinja2 (server-rendered), not Next.js/FastAPI: no separate JS build, trivial to TDD via
`app.test_client()`, and matches "a foothold, not the final UI."

## SQLite schema (`poc/jobhub_poc/schema.sql`)

Freshness/purge is keyed **solely on `first_seen_at`** (server-assigned at load time), never on
the source's own posted-date field — that field's presence/format is unconfirmed (only `id`,
`site`, `title`, `companyName` are confirmed to exist on every job from the old Spring client
code). The source date is stored opportunistically as `posted_at_source` for display only.

```sql
CREATE TABLE IF NOT EXISTS jobs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    dedupe_key        TEXT NOT NULL UNIQUE,   -- external id if present, else sha256(site|title|company|location)
    external_job_id   TEXT,
    source_site       TEXT NOT NULL,
    search_term       TEXT,
    title             TEXT NOT NULL,
    company_name      TEXT,
    location          TEXT,
    description       TEXT,
    employment_type   TEXT,
    is_remote         INTEGER NOT NULL DEFAULT 0,
    apply_url         TEXT,
    posted_at_source  TEXT,                   -- raw, opportunistic, NEVER used for purge
    first_seen_at     TEXT NOT NULL,          -- canonical freshness signal, set once
    last_seen_at      TEXT NOT NULL,          -- updated every re-scrape hit
    raw_json          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_title         ON jobs(title);
CREATE INDEX IF NOT EXISTS idx_jobs_location      ON jobs(location);
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen_at ON jobs(first_seen_at);

CREATE TABLE IF NOT EXISTS app_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,              -- werkzeug.security
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_number TEXT NOT NULL,
    title_keyword TEXT,                       -- substring match, NULL/'' = match any
    location_keyword TEXT,
    created_by_user_id INTEGER REFERENCES app_users(id),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alert_subscriptions_active ON alert_subscriptions(is_active);

CREATE TABLE IF NOT EXISTS alerts_sent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id INTEGER NOT NULL REFERENCES alert_subscriptions(id),
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    notifier_backend TEXT NOT NULL,           -- 'console' | 'whatsapp' (future)
    message TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    status TEXT NOT NULL,                     -- 'SENT' | 'FAILED'
    UNIQUE(subscription_id, job_id)           -- idempotent: never double-alert
);
```

`load_dump.py` upserts on `dedupe_key` conflict, updating `last_seen_at` and content fields but
never touching `id`/`dedupe_key`/`first_seen_at`. It also emits the list of genuinely **new**
(inserted, not updated) job ids, which `run_alerts.py` consumes directly — avoiding a flaky
timestamp-window heuristic for "what's new."

Known, deliberate simplification (documented in `poc/README.md`): an evergreen listing that
keeps reappearing every scrape still gets purged 15 days after we *first* saw it, not 15 days
after it stops appearing. Fine for a manually-triggered POC; flag as a future decision if this
starts running on a real recurring schedule.

## Orchestration

Manual-trigger scripts are the Saturday-safe default; cron/systemd auto-scheduling is a stretch
goal, not a dependency. `poc/scripts/run_pipeline.sh` runs **from harita**, using its existing
passwordless SSH to both hosts (routing the JSON handoff through harita, since pi05↔pi09 trust
is unconfirmed):

1. `ssh pi05 '... python dump_jobs.py'` — scrape, write timestamped JSON under `scraper/dumps/`.
2. `scp` the latest dump: pi05 → harita → pi09.
3. `ssh pi09 '... python -m jobhub_poc.loader.load_dump <dump> --new-ids-out /tmp/new_ids.json'`
4. `ssh pi09 '... python -m jobhub_poc.loader.purge'`
5. `ssh pi09 '... python -m jobhub_poc.alerts.run_alerts --new-ids /tmp/new_ids.json'`

**pi05 setup** (needs sudo, via the `.env.sudo.password` file the user is providing — never
typed in chat, piped locally on that host: `sudo -S apt-get install -y nodejs npm build-essential
< ~/.env.sudo.password`): `apt-cache policy nodejs` on pi05 confirms `20.19.2` is available,
matching the `node:20-slim` image the EverJobs bundle was built for. Stage the existing built
artifact — `~/workspace/projects/aavartlabs/JobHubNG/ever-jobs-docker/{dist,package.json,
package-lock.json}` from pi09 — onto pi05 via harita, then run `npm install --production
--legacy-peer-deps` **natively on pi05** (pi05 is aarch64; pi09's `node_modules` were built for
x86_64 and can't be copied — `better-sqlite3` is a native addon). `build-essential` covers the
case where no prebuilt arm64 binary exists and `node-gyp` must compile from source. Run the
server with `nohup node dist/apps/api/main.js &`, env `PORT=3001`, `EVER_JOBS_STORE=memory`,
`DEFAULT_SITE_NAMES=google` (as-built: the only bucket actually exercised so far).

**pi09 setup**: nothing new to install — Docker and Python 3.13+venv already present. Plain
`python3 -m venv .venv && pip install -r requirements.txt`, run Flask directly on port 8100
(`WEB_PORT=8100`), on a network/port distinct from the live `jobhub` docker network (which is
currently serving `jobhubs.aavartlabs.com` — confirmed still returning HTTP 200 — leave it
alone). Containerizing `jobhub_poc` in Docker on pi09 is a should-have (AWS-portability optics),
not a Saturday blocker — plain venv + nohup is the fallback (and, as-built, still what's running).

Do **not** touch the orphaned/crashed containers on pi09 (`jobhub-platform-api` crash-looping,
`jobhub-ever-jobs` never-started, `jobhub-agent-runtime` stale 32h-old leftover with no
corresponding source in git) as part of this work — new ports/network don't conflict. Cleanup is
an optional final step only after the new stack is verified working.

## Config (`poc/.env.example` — separate file from the root one, which stays as historical
documentation of the retired stack)

```
EVER_JOBS_API_URL=http://localhost:3001
EVER_JOBS_API_KEY=
EVER_JOBS_SITE_NAMES=google
REQUEST_TIMEOUT_SECONDS=240
SEARCH_TERMS=software engineer,data analyst,product manager
RESULTS_PER_TERM=10
DUMP_DIR=./dumps

JOBHUB_SQLITE_PATH=./data/jobhub.db
PURGE_WINDOW_DAYS=15

WEB_PORT=8100
WEB_SECRET_KEY=change-me-please-32-bytes-min
WEB_ADMIN_USERNAME=admin
WEB_ADMIN_PASSWORD=change-me

NOTIFIER_BACKEND=console
# fast-follow, not wired Saturday:
# NOTIFIER_BACKEND=whatsapp
# WHATSAPP_GATEWAY_URL=
# WHATSAPP_GATEWAY_API_KEY=
```

Note for requirement #3's "location" filter: the old Spring `EverJobsClient` never actually sent
a location parameter to EverJobs — only `{query, results}`. So "location" in the new web UI is a
client-side filter over whatever `location` field happens to be present in each scraped job, not
a scrape-time control. EverJobs can't be asked "give me jobs in Bangalore."

## TDD plan

Real red-green-refactor rigor on: loader (dedup/upsert/purge) and alert matching — the actual
logic. Lighter route/response assertions (Flask test client, no live server) for the web layer,
appropriate for a "foothold, not final UI."

Order of first tests, each written failing before the code that satisfies it:
1. `scraper/tests/test_everjobs_client.py` — `search()` posts the right payload/headers via
   `requests_mock`, parses the `jobs` array; then empty-array, non-200, timeout handling.
2. `tests/test_load_dump.py` — insert sets `first_seen_at == last_seen_at`; re-loading the same
   job updates `last_seen_at` only and doesn't duplicate; missing `id` falls back to the
   content-hash `dedupe_key` and still dedupes across dumps; missing optional fields don't raise;
   `raw_json` round-trips exactly.
3. `tests/test_purge.py` — deletes rows older than the window, keeps newer ones; boundary case
   at exactly the window edge (kept, not deleted); no-op on a clean table.
4. `tests/test_matcher.py` — case-insensitive title/location substring match; empty criteria
   matches everything; only `new_job_ids` are considered; inactive subscriptions are skipped.
5. `tests/test_notifier.py` — `ConsoleNotifier` prints + writes `alerts_sent`; double-send for
   the same `(subscription_id, job_id)` is caught gracefully, not a crash; unknown backend raises.
6. `tests/test_webapp_*.py` — `/jobs` redirects to `/login` unauthenticated; valid login sets
   session; title/location filters narrow results; freshness sort orders by `first_seen_at DESC`;
   `/alerts/register` POST creates a row; malformed phone gets a 400.

As-built: 33 `poc/` tests + 10 `poc/scraper/` tests, all green.

## Saturday cut line

**Must-have (target: functionally done by Friday evening, Saturday is buffer/polish):**
1. `scraper/` produces a real, non-empty `dumps/*.json` from pi05 against the live EverJobs
   server — or, if the live scrape genuinely doesn't pan out, the identical `{"jobs":[...]}`
   contract is satisfied by a captured fixture and the demo narrative says so plainly.
   **As-built: live scraping works** (see "Resolved during implementation" above).
2. Loader (dedup + `first_seen_at`/`last_seen_at` + the three indexes) — fully TDD'd. **Done.**
3. Purge — TDD'd, demoable by backdating a row and re-running. **Done, verified live.**
4. Web app on pi09:8100, login-gated, job list filterable/sortable by title/location/freshness.
   **Done, verified live over HTTP.**
5. Alert registration + matcher + `ConsoleNotifier`, demonstrably firing (and not double-firing)
   after a pipeline run. **Done, verified live (10 real matches fired, re-run confirmed no
   duplicate sends).**
6. `run_pipeline.sh` runs end-to-end from harita over the existing SSH keys. **Done.**
7. Everything env-configured per the section above — no hardcoded hosts/ports/keys/paths. **Done.**

**Should-have:** Dockerize `jobhub_poc` on pi09 on a new network/port. **Done** — it now
runs as the `jobhub-web` container, which also took over serving `jobhubs.aavartlabs.com`
directly (reusing the existing Cloudflare Tunnel rather than a second hostname, since the
tunnel's routing target is fixed remotely and can't be changed from here — see
`poc/README.md`). Covering more than one EverJobs site is still not done (only the
`google` bucket has been exercised).

**Explicit stretch, not Saturday:**
- cron/systemd auto-scheduling of the pipeline. **Done** — see `poc/README.md`'s
  "Scheduling" note: a systemd user timer on harita runs the pipeline every 6 hours,
  EverJobs on pi05 is a proper systemd service (`Restart=always`, boot-enabled), and
  pi09's containers already auto-restart via Docker's `restart: unless-stopped`.
- a real WhatsApp notifier. **Done** — built `poc/whatsapp-sender/` (hand-rolled `baileys`
  service, not OpenWA/whatsapp-gateway after all — see that directory's README for why),
  QR-paired with a real number, and confirmed delivered on real phones for `sre`,
  "product manager", and "operations" alert subscriptions.
- multi-user account management. Still not done (one seeded demo login is enough so far).

## Verification

```bash
# 1. Real scraped data on pi05
ssh pi05 'cd ~/jobhub-poc/scraper && python3 -m json.tool dumps/$(ls -t dumps | head -1) | head -40'

# 2. End-to-end pipeline
bash poc/scripts/run_pipeline.sh   # from harita, exit 0

# 3. SQLite state on pi09 (no sqlite3 CLI on pi09 -- use python3's stdlib sqlite3 module instead)
ssh pi09 'cd ~/jobhub-poc && python3 -c "
import sqlite3
conn = sqlite3.connect(\"data/jobhub.db\")
print([dict(r) for r in conn.execute(\"SELECT source_site, COUNT(*) c FROM jobs GROUP BY source_site\")])
"'

# 4. Purge correctness
ssh pi09 'cd ~/jobhub-poc && python3 -c "
import sqlite3
conn = sqlite3.connect(\"data/jobhub.db\")
conn.execute(\"UPDATE jobs SET first_seen_at = datetime(\\\"now\\\", \\\"-16 days\\\") WHERE id = 1\")
conn.commit()
"'
ssh pi09 'cd ~/jobhub-poc && .venv/bin/python -m jobhub_poc.loader.purge'

# 5. Browser: http://192.168.2.174:8100/jobs redirects to /login; log in; filter/sort works.

# 6. Alert stub, with idempotency proof: register a subscription, run the pipeline twice,
#    confirm alerts_sent grows once then stays flat.

# 7. Test suites
(cd poc && .venv/bin/pytest -v)
(cd poc/scraper && .venv/bin/pytest -v)
```

All of the above has been run against the real hosts, not just described.

## Explicitly out of scope for this plan

- Touching/fixing the old `apps/platform-api`/`apps/web`/Postgres stack, or the crashed/orphaned
  containers on pi09.
- Updating root `CLAUDE.md`/`AGENTS.md`/`README.md`/`tasks_*.md` to describe this new pivot
  (they currently and correctly describe the retired stack) — worth a fast-follow once the POC
  stabilizes, not part of this build.
- Any real WhatsApp send integration (see stretch section).
- Automated scheduling.
