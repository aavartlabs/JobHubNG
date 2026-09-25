# JobsHub on the Hostinger server (testprepup)

This runbook moves the whole site, the web app and the scraper, from the two Raspberry Pis
onto one server. It runs first at `jobshub-dev.aavartlabs.com`, side by side with the live
site, then takes over `jobshub.aavartlabs.com`.

The server is **shared with other production sites** (CRM, DIP, aanvik, testprepup.com) and
has no swap. So:
- every JobsHub container has a hard memory and CPU cap (`docker-compose.hostinger.yml`);
- nothing is published beyond `127.0.0.1` (Docker's published ports bypass `ufw`);
- the only public way in is the host's shared `edge-nginx`, and only from Cloudflare.

**Every step on that server needs Sanjay's go.**

## What runs where

```
Browser → Cloudflare (proxied DNS, TLS, Access on dev) → testprepup:443 edge-nginx (shared)
  → jobhub-web:3000 over the "edge" network (deploy/nginx/<host>.conf)
~/aavartlabs/jobshub/            rsync of poc/ (not a git checkout)
  containers   web, auth-service, telegram, ai (queue worker), everjobs   (tunnel, whatsapp: off)
  data/jobhub.db  auth-service/data/auth.db  scraper/data/warehouse.db   (SQLite, local disk)
  .venv/, scraper/.venv/         host venvs for the pipeline CLIs
  logs/                          cron job logs (scripts/cron_job.sh)
~/.jobshub-r2.env (0600)         R2 credentials for backups and cold export
```

**AI:** `AI_BACKEND=openrouter`.
- **Resume work** (`AI_MODELS_WRITE`) goes only to models that don't train on it.
- **Public job text** (`AI_MODELS_JOBS`) may use any model, and direct DeepSeek/Meta keys
  when OpenRouter is down.
- The chains come from `scripts/ai_bakeoff.py` (see "Model choice" below).

## 1. Set up (nothing public)

1. **Code:** `rsync -a --exclude .env --exclude data/ --exclude .venv/ --exclude
   'whatsapp-sender/auth_info/' --exclude 'auth-service/data/' --exclude secrets/ poc/
   testprepup:aavartlabs/jobshub/`. Also copy EverJobs' bundle into `everjobs/runtime/`
   (`everjobs/README.md`).
2. **Network:** `docker network create jobhub`. The shared `edge` network already exists.
3. **Env files.** Copy them straight from pi09 to the server, never through this repo;
   key files are one bare token each, on harita.
   - `.env`, from pi09's, then set:

     | Setting | Value |
     |---|---|
     | `WEB_ORIGIN` | `https://jobshub-dev.aavartlabs.com` |
     | `TURNSTILE_HOSTNAMES` | `jobshub-dev.aavartlabs.com` |
     | `LEGACY_HOSTS` | empty |
     | `NOTIFIER_BACKEND` | `console` (no digests from dev) |
     | `AI_BACKEND` | `openrouter` |
     | `OPENROUTER_API_KEY` | from harita `~/.env.openrouter` |
     | `AI_MODELS_WRITE`, `AI_MODELS_JOBS` | from the bake-off |
     | `DEEPSEEK_API_KEY` | from `~/.env.deepseek` |
     | `META_API_KEY` | from `~/.env.meta`; plus `META_BASE_URL=https://api.meta.ai/v1`, `META_MODEL=muse-spark-1.3-contributor`, `META_JSON=schema`, `META_REASONING_EFFORT=minimal`. `AI_MODELS_JOBS=direct:meta,openai/gpt-6-luna-pro,deepseek/deepseek-v4-flash`. Muse contributor trains on prompts, so it gets public job text only (enforced in code). |
     | `TYPESAFE_API_KEY` | from `~/.env.typesafe.ai` (Phase B) |
     | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME` | the **dev bot's** |
     | `RESUME_ENCRYPTION_KEY` | kept as on pi09, so copied resumes still decrypt |

   - `auth-service/.env`: from pi09's, unchanged.
   - `scraper/.env`: `EVER_JOBS_API_URL=http://127.0.0.1:3001`.
   - `~/.jobshub-r2.env` (0600):
     - `MINIO_ENDPOINT=https://<account>.r2.cloudflarestorage.com`
     - `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY` (the R2 token's pair)
     - `MINIO_BUCKET`
   The server's Python has no `ensurepip`, and adding it needs sudo. So the venvs are made
   with `uv` (`~/.local/bin/uv`, user-level): `uv venv --python /usr/bin/python3 .venv &&
   uv pip install --python .venv/bin/python -r requirements.txt`, and the same in
   `scraper/`.
4. **mc:** `~/bin/mc`, linux-amd64, the same release as pi09 (`RELEASE.2025-08-13T08-35-41Z`).
   MinIO no longer serves free `mc` downloads: that path returns 410, and only the paid
   AIStor client is offered. So it's built from source in a throwaway container:
   `podman run --rm -v $PWD:/out golang:1.24 sh -c 'git clone --depth 1 --branch
   RELEASE.2025-08-13T08-35-41Z https://github.com/minio/mc /src && cd /src &&
   CGO_ENABLED=0 go build -trimpath -o /out/mc .'`, then copy it to the server. Check R2 with
   `backup_to_minio.sh` on a scratch DB: upload, `stat` shows the sha256, download,
   `integrity_check`.
5. **Venvs:** see step 3's note (uv).
6. **Seed the databases:** SQLite online-backup copies of pi09's `jobhub.db` and `auth.db`
   and pi05's `warehouse.db`, copied over, then `PRAGMA integrity_check`. Dev data is
   disposable: it's replaced by fresh copies at the switch.
7. **Containers:**
   ```bash
   C="docker compose -f docker-compose.yml -f docker-compose.hostinger.yml"   # project name jobhub-poc, set in the override
   $C build && $C up -d
   ```
   This starts web, auth-service, telegram, ai and everjobs. The tunnel and WhatsApp are
   profiles and stay off.

## 2. Ingress for dev

1. **DNS:** `jobshub-dev.aavartlabs.com` is proxied to this server (done by Sanjay).
2. **Cloudflare Access app** on `jobshub-dev`: Sanjay's email only, plus a **bypass** policy
   for `/telegram/webhook` (Telegram's calls are still checked with the webhook secret).
3. **nginx:**
   ```bash
   cp poc/deploy/nginx/jobshub-dev.aavartlabs.com.conf ~/projects/edge/nginx/conf.d/
   docker exec edge-nginx nginx -t && docker exec edge-nginx nginx -s reload
   ```
   The file reuses the host's testprepup.com certificate; the zone's SSL mode is "Full", as
   for crm/dip. It admits only Cloudflare's addresses and overwrites `CF-Connecting-IP`
   with the verified visitor IP. It resolves `jobhub-web` per request, so a stopped JobsHub
   can't break the shared nginx's reload.

   **Rollback:** remove the file, then `nginx -t && nginx -s reload`.
4. **Checks:**
   - Through Cloudflare: the Access login appears, then the site returns 200.
   - Straight to the server's IP with that Host header: 403.
   - The other sites still return 200.

## 3. Trial (1–2 days)

- **Pipeline** by hand, then from cron:
  `scripts/cron_job.sh pipeline env SUPPRESS_ALERTS=1 SCRAPER_HOST=local scripts/run_pipeline_warehouse.sh`.
  Compare sweep size, new jobs and enrich counts with pi05's `ingest_runs`. **Job boards may
  block a datacenter IP.** If the sweep is much smaller, keep EverJobs and ingest on pi05 and
  have it push the sweep here.
- **Account flows:** sign-up OTP, Turnstile, Telegram linking on the dev bot, a resume upload
  and a tailoring.
- **Backups:** one backup to R2 and the restore drill against it.
- **Load:** `docker stats` within the caps (everjobs peaked at 2.6 GB on pi05; cap 3 GB), and
  the neighbours' health stays green.

## 4. Cron

The server's clock is **UTC** (checked 2026-09-25), so these are the IST times converted:
- pipeline at 00/06/12/18 IST;
- backup at 02:30 IST;
- drill on Sunday at 04:00 IST (Saturday 22:30 UTC);
- cold export at 03:30 IST on the 2nd.

```cron
30 0,6,12,18 * * * cd ~/aavartlabs/jobshub && scripts/cron_job.sh pipeline env SCRAPER_HOST=local scripts/run_pipeline_warehouse.sh
0 21 * * *        cd ~/aavartlabs/jobshub && scripts/cron_job.sh backup env JOBSHUB_MINIO_ENV=$HOME/.jobshub-r2.env scripts/nightly_backup_local.sh
30 22 * * 6       cd ~/aavartlabs/jobshub && scripts/cron_job.sh restore-drill env JOBSHUB_MINIO_ENV=$HOME/.jobshub-r2.env JOBSHUB_DRILL_APP_HOST=hostinger JOBSHUB_DRILL_WAREHOUSE_HOST=hostinger .venv/bin/python -m jobhub_poc.ops.restore_drill
0 22 1 * *        cd ~/aavartlabs/jobshub && scripts/cron_job.sh cold-export bash -c 'cd scraper && JOBSHUB_MINIO_ENV=$HOME/.jobshub-r2.env .venv/bin/python cold_export.py'
```

A failed job sends the admin a Telegram message (`cron_job.sh` → `ops.alert_admin`).

On R2, set lifecycle rules for `backups/daily/`, `weekly/` and `monthly/` at 14, 84 and 365
days. Optionally add a bucket lock on `backups/`: the R2 token can delete, which the old
MinIO user couldn't.

## 5. The switch

1. pi09: `systemctl --user stop jobhub-pipeline.timer`.
2. Fresh online-backup copies of the three databases, copied over, then `integrity_check`.
3. `.env`:
   - `WEB_ORIGIN=https://jobshub.aavartlabs.com`
   - `TURNSTILE_HOSTNAMES=jobshub.aavartlabs.com`
   - `LEGACY_HOSTS=jobhubs.aavartlabs.com`
   - the **prod** Telegram bot token and username
   - `RESUME_CONSENT_SINCE=<now, ISO UTC>`
   - `NOTIFIER_BACKEND=live`

   Then `$C up -d`.
4. Copy the nginx file as `jobshub.aavartlabs.com.conf` with
   `server_name jobshub.aavartlabs.com jobhubs.aavartlabs.com;`, then `nginx -t` and reload.
5. Cloudflare DNS: `jobshub` and `jobhubs` move from the tunnel CNAME to proxied records for
   this server.
6. pi09: `docker stop jobhub-web jobhub-ai jobhub-telegram jobhub-cloudflare-tunnel`.
7. Checks: site 200, sign-in, one pipeline run, one Telegram digest, a resume tailoring.
8. After two quiet weeks: delete the tunnel in the Cloudflare dashboard, and disable the Pis'
   units for good.

**Rollback:**
1. DNS back to the tunnel CNAME.
2. pi09: `docker start` its four containers and the pipeline timer.
3. Server: cron lines commented out.

Anything written on the server in between (accounts, alerts, saved jobs) would need copying
back. Take a backup first.

## Model choice

`scripts/ai_bakeoff.py` scores each candidate with the site's own checks. Rerun it when a
new model is worth trying.
- **tailor:** 16 made-up resume × job pairs, measuring fabrications caught and anything
  ungrounded left over (must be 0).
- **parse:** 4 made-up resumes.
- **jobs:** the fixtures plus real public postings.

```bash
OPENROUTER_API_KEY=... .venv/bin/python scripts/ai_bakeoff.py --write-models A,B --jobs-models C,D \
    --jobs-db data/jobhub.db --real-jobs 50 --out bakeoff.json
```

## WhatsApp fallback

It's off here (compose profile `whatsapp`); admin messages go by Telegram. Never run two
sessions on one number.
