# Local Runbook

**This repo contains two generations of the project — only `poc/` is live.** See `CLAUDE.md`
for the full picture. The steps below run the live `poc/` pipeline locally; the retired
Phase 0/1 Spring Boot runbook (`apps/`) is kept further down for context only.

## `poc/` (live system)

1. `cd poc && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
2. `cp .env.example .env` — defaults are fine for a local-only run
3. `.venv/bin/python scripts/seed_demo_data.py` — loads
   `fixtures/sample_everjobs_response_real.json` so there's data to browse without a live
   scraper
4. `.venv/bin/python -m jobhub_poc.webapp.app` — http://localhost:8100/jobs

Browsing (`/jobs`, `/api/jobs`) is public and needs nothing else. There is no shared demo
login any more — `scripts/seed_demo_user.py` and the `app_users` table are gone, replaced
by real self-service accounts (see `docs/superpowers/specs/2026-09-22-user-accounts-auth-design.md`).

### Accounts, locally

Everything under `/alerts/*` requires a verified account, which lives in a second service:
`poc/auth-service/` (Node + Better Auth, own `auth.db`). Flask reverse-proxies `/auth/*` to
it, so it has to be running for `/login`, `/register`, `/verify` or `/alerts/*` to do
anything:

```bash
cd poc/auth-service
cp .env.example .env            # read the comments -- several defaults are dev-only
npm install
npx --yes @better-auth/cli@1.4.21 migrate --yes   # once, per fresh AUTH_DB_PATH
npm start                        # :3200; Flask's AUTH_SERVICE_URL default points here
```

**You cannot fully register an account locally without real credentials.** Signup requires
both an email OTP (sent via Resend — needs a real `RESEND_API_KEY` and a verified sending
domain) and a mobile OTP (sent via the `whatsapp-sender` gateway — needs a QR-paired
WhatsApp number). Without those, `/register` creates the account but neither code is ever
delivered, so it can never become usable. What you *can* exercise locally without them:
the public job browsing, the unit test suites, and the redirect behaviour of the gated
routes. Full registration is verified against the real pi09 deployment, not locally.

To exercise the real pipeline locally instead of the bundled fixture (requires a reachable
EverJobs instance, `EVER_JOBS_API_URL` in `.env`), from `poc/`:
```bash
make dump                    # scrapes into scraper/dumps/*.json
make load DUMP=scraper/dumps/<the-file>.json
make purge
make alerts
```
`make pipeline` instead runs `scripts/run_pipeline.sh`, which assumes SSH access to the real
`pi05`/`pi09` hosts and is not meant for a purely local run.

### Cleanup

Delete `poc/data/jobhub.db` to reset job/alert state, and `poc/auth-service/`'s `auth.db`
(wherever `AUTH_DB_PATH` points) to reset accounts. No Docker or Postgres involvement for a
local-only run — the `docker-compose.yml`/`Dockerfile` in `poc/` are for the pi09 deployment
only.

## Real deployment (pi05 / pi09)

Not reproducible locally. See `poc/README.md`'s "Deployment" section and `CLAUDE.md` for the
host topology, systemd scheduling (pipeline every 6 hours, on pi09 itself as of 2026-09-22;
EverJobs as a systemd service on pi05), and why the Cloudflare Tunnel's routing target can't
be changed from here.

## Retired: Phase 0/1 runbook (`apps/`, Spring Boot + Next.js + Postgres, not live)

1. `docker compose up -d postgres`
2. `cd apps/platform-api && ./mvnw spring-boot:run`
3. `cd apps/web && npm install && npm run dev`
4. Open `http://localhost:3000`
5. Sign in using a demo account.
6. Admin can inspect the audit/outbox counts in the portal.
7. Optional: start the agent runtime on port 8090; it was intentionally a health-only
   scaffold in Phase 0/1 and does not exist as `apps/agent-runtime` in this repo.

### Cleanup

`docker compose down`

To remove DB data too: `docker compose down -v`.
