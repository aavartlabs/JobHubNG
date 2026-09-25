# JobsHub on the Hostinger server (testprepup)

This runbook moves the whole site, the web app and the scraper, from the two Raspberry Pis
onto one server. That server is **shared with other production sites** (CRM, DIP, aanvik,
testprepup) and has no swap.

The rules here follow from that:
- Every container gets a hard memory and CPU cap (`docker-compose.hostinger.yml`).
- Nothing is published beyond `127.0.0.1`. Docker-published ports bypass `ufw`, so the
  loopback binds are the firewall.
- JobsHub keeps its own `jobhub` network.
- The shared `edge-nginx` isn't touched: the public keeps reaching the site through the
  Cloudflare Tunnel, as on pi09.

Every step on that server needs Sanjay's go.

## Layout on the server

```
~/aavartlabs/jobshub/            rsync of poc/ (like ~/jobhub-poc on pi09; not a git checkout)
  .env, auth-service/.env        copied from pi09, then edited (see below)
  secrets/cloudflare-tunnel.token
  data/jobhub.db                 serving DB        (was pi09)
  auth-service/data/auth.db      accounts          (was pi09)
  scraper/data/warehouse.db      warehouse         (was pi05)
  .venv/, scraper/.venv/         host venvs for the pipeline CLIs (python3.12 is there)
  logs/                          cron job logs (scripts/cron_job.sh)
```

## 1. Set up (no traffic yet)

1. Copy the code: `rsync -a --exclude .env --exclude data/ --exclude .venv/ --exclude
   'whatsapp-sender/auth_info/' --exclude 'auth-service/data/' --exclude secrets/ poc/
   testprepup:aavartlabs/jobshub/`.
2. Copy EverJobs' bundle into `everjobs/runtime/` first (`everjobs/README.md`).
3. Create the network: `docker network create jobhub`.
4. Set up the env files. Copy pi09's `.env` and `auth-service/.env` (scp from pi09 to the
   server; never through this repo), then set:
   - `AI_BACKEND=workers_ai`, `WORKERS_AI_ACCOUNT_ID`, `WORKERS_AI_GATEWAY`,
     `WORKERS_AI_TOKEN` (and `WORKERS_AI_GATEWAY_TOKEN` for an authenticated gateway).
     Turn logging off on the gateway itself too.
   - `NOTIFIER_BACKEND=console` until the cutover.
   - `EVER_JOBS_API_URL=http://127.0.0.1:3001` in `scraper/.env`.
5. Create the venvs:
   - `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
   - the same in `scraper/`
6. Start the containers except the tunnel:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.hostinger.yml build
   docker compose -f docker-compose.yml -f docker-compose.hostinger.yml up -d everjobs web auth-service ai
   ```
   `telegram` can wait until the cutover. Starting it early is harmless, though: on boot
   it re-registers the same webhook URL and secret, and Telegram keeps posting to the
   public URL, which reaches pi09 until the tunnel moves.

## 2. Shadow run (1–2 days, nothing public)

Seed the databases:
- `warehouse.db` from pi05.
- `jobhub.db` and `auth.db` from pi09.

Use SQLite online-backup copies, the same method as `scripts/pull_backup.sh`. Then run the
pipeline by hand, with alerts off:

```bash
SUPPRESS_ALERTS=1 scripts/cron_job.sh pipeline env SCRAPER_HOST=local scripts/run_pipeline_warehouse.sh
```

Compare against pi05's `ingest_runs` for the same hours:
- sweep size (jobs seen)
- new jobs
- enrich counts

**Job boards may block a datacenter IP.** If the sweep is much smaller, keep EverJobs and
ingest on pi05 and have pi05 push each sweep here instead (plan fallback).

Also watch:
- `docker stats`: everjobs peaked at 2.6 GB on pi05 (cap 3 GB).
- The other sites' health checks, which must stay green.

## 3. Cutover (a few minutes)

1. pi09: `systemctl --user stop jobhub-pipeline.timer`.
2. Final copies of the three databases (online backup), copied over. Run `PRAGMA
   integrity_check` on each.
3. Set `RESUME_CONSENT_SINCE=<now, ISO UTC>` in `.env`. Everyone who uploaded a resume is
   asked to agree to the Workers AI wording before more AI work (`resume_consent.py`).
4. Server: `up -d` the stack including `telegram`. pi09: `docker stop jobhub-telegram jobhub-cloudflare-tunnel jobhub-web jobhub-ai`.
5. Server: `up -d tunnel` (same token file). Check that the site returns 200 and that sign-in works.
6. Set `NOTIFIER_BACKEND=live`, then install the cron lines:
   ```cron
   0 0,6,12,18 * * * cd ~/aavartlabs/jobshub && scripts/cron_job.sh pipeline env SCRAPER_HOST=local scripts/run_pipeline_warehouse.sh
   ```
   Cron runs in the server's time zone. Check it (`timedatectl`) and shift the hours if it
   isn't IST.

   **Not scheduled here: the monthly cold export** (`scraper/cold_export.py`). It uploads to
   MinIO, which this server can't reach. Until it's reworked to be pulled like the backups,
   the warehouse keeps its old history. That's a few MB a day, against 163 GB free.
7. Backups on pi09:
   - Point `jobshub-backup.service` at `scripts/pull_backup.sh` (label `hostinger`).
   - Set `JOBSHUB_DRILL_APP_HOST=hostinger` and `JOBSHUB_DRILL_WAREHOUSE_HOST=hostinger`
     for the restore drill.

## Rollback

1. Server: `docker stop jobhub-cloudflare-tunnel jobhub-telegram` and comment out the cron lines.
2. pi09: `docker start jobhub-web jobhub-ai jobhub-telegram jobhub-cloudflare-tunnel`, then
   `systemctl --user start jobhub-pipeline.timer`.

The Pis keep their data and units, disabled but not deleted, for 2 weeks after the cutover.
Anything written on the server in between (new accounts, alerts, saved jobs) would need
copying back. Before rolling back, take a pull of the server's DBs first.

## WhatsApp fallback

It's off here (compose profile `whatsapp`); admin messages go by Telegram. To keep it,
either move `whatsapp-sender/auth_info/` from pi09 with pi09's container stopped for good,
or pair it again. Never run two sessions on one number.
