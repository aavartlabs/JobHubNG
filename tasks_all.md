# JobHubNG — Task List

**Updated:** 2026-09-22

**Supersedes the 2-week Spring Boot/Flowable/Kafka delivery plan this file used to track**
(dated 2026-09-11, against the LLD/E2E-deck architecture, with Madhu as product owner and
Codex as implementation accelerator). That plan and the stack it targeted were abandoned on
2026-09-16 for `poc/` — a minimal Python pipeline (scraper → SQLite → Flask+TS web app →
WhatsApp alerts) that already runs, live, on Raspberry Pi hardware (pi05/pi09), orchestrated
from a third host (harita). See `CLAUDE.md` for the full architecture and `poc/PLAN.md` for
the pivot rationale. `tasks_sanjay.md` was a companion to the same retired plan and is
equally stale — not updated here.

## Status: what's built and live

Per `poc/PLAN.md`'s cut line, all of this is done and has been verified against the real
hosts, not just unit-tested:

| Area | Status | Notes |
| --- | --- | --- |
| Scraper (pi05) | Done | `dump_jobs.py` against live EverJobs, client-side filter/cap by `SEARCH_TERMS` |
| Loader + purge (pi09) | Done | dedupe/upsert, `first_seen_at`-only freshness, 15-day purge window |
| Web app (pi09, Docker) | Done | Flask + JSON API + TS frontend, login-gated, filter/sort/paginate |
| Alert registration + matching | Done | keyword substring match on newly-inserted jobs only |
| WhatsApp delivery | Done | `whatsapp-sender/` (baileys), real number paired, delivery-confirmed (see below) |
| Automated scheduling | Done | systemd timer on harita (6h), EverJobs as a systemd service on pi05 |
| Dockerized web deployment | Done | `jobhub-web` container serves `jobhubs.aavartlabs.com` via the existing Cloudflare Tunnel |

## Open items (as of 2026-09-22 operational check)

| ID | Item | Status | Notes |
| --- | --- | --- | --- |
| T1 | WhatsApp gateway reported "sent" without confirming actual delivery | **Fixed 2026-09-22** | `/send` now waits for baileys' `SERVER_ACK` via a new `ack-tracker.js` before reporting success (`poc/whatsapp-sender/src/`). This confirms WhatsApp's servers received the message, not that the recipient's device has it (`DELIVERY_ACK`) — a deliberate, cheaper stopping point. |
| T2 | A failed alert send is never retried | Open | `run_alerts.py` only ever considers job ids that were genuinely new in *that* pipeline run (`matcher.find_matches(conn, new_ids)`); once a job ages out of "new," a prior `FAILED` row for it is never reconsidered, and `Notifier.send()`'s existing-row check skips retrying regardless of status anyway. Was low-stakes when sends rarely failed; more consequential now that delivery confirmation (T1) means genuine failures actually get flagged as `FAILED` instead of silently `SENT`. |
| T3 | Pipeline's post-reboot catch-up run fails instantly | Open, deferred | The systemd `Persistent=true` catch-up run that fires immediately after a harita reboot dies in <1s (`status=255`); the regular 6-hourly runs are unaffected and self-heal by the next scheduled slot. Likely a network-not-ready-at-boot race in the unit's ordering. Not urgent — flagged 2026-09-22, left for later per explicit decision. |
| T4 | No CI coverage for `poc/` or `whatsapp-sender` | Open | `.github/workflows/ci.yml` only builds/tests the retired `apps/` stack. `poc/`'s and `poc/scraper/`'s pytest suites and `whatsapp-sender`'s `node --test` suite are verified manually only. |
| T5 | No multi-user auth | Open, by design so far | One shared demo login gates the whole app; no roles, no per-user accounts. Not attempted yet — see `poc/PLAN.md`'s stretch list. |
| T6 | Only one EverJobs site bucket (`google`) exercised | Open | Other buckets/sites were never tried; unknown whether they behave the same way (ignoring query params, same response shape). |

## If/when this needs to scale

Not a redesign — just where the current design's seams already are, since scaling was
named as a goal without a specific trigger yet:

- **More job volume / more sources.** Today: one synchronous EverJobs call per pipeline
  run (~2.5 min, ~15k raw jobs from a single `google` bucket), one SQLite file, no queue.
  Adding more site buckets or running scrapes more often is mostly config (`EVER_JOBS_SITE_NAMES`,
  `SEARCH_TERMS`, pipeline cadence) until either the scrape itself becomes the bottleneck
  (would need to parallelize/stagger buckets) or SQLite write contention becomes real (would
  need to swap in Postgres — `db.py`'s `sqlite3.Connection`-based interface is the only
  place that assumes SQLite specifically).
- **More subscribers / alert volume.** Today: `run_alerts.py` sends one HTTP POST per
  match, sequentially, in a plain `for` loop — no batching, no rate-limit awareness of
  WhatsApp's own throttling. T2 (no retry) gets more expensive as subscriber count grows,
  since more sends means more chances for a transient failure to permanently drop an alert.
  Fixing T2 is the natural first step before pushing alert volume much higher.
- **Moving off Raspberry Pi hardware.** Already largely free: every host/port/key/path is
  env-configured (`poc/.env.example`, `poc/scraper/.env`), and `run_pipeline.sh` just needs
  working SSH aliases to whatever hosts take over the `pi05`/`pi09` roles — no code changes
  implied. The one host-specific unknown is whether EverJobs' Playwright/Chromium dependency
  (confirmed via string search in the bundle, never fully characterized) behaves the same on
  a non-ARM, non-Pi host; worth a real check before assuming a lift-and-shift is trivial.

## Reference map

| Doc | Role |
| --- | --- |
| `CLAUDE.md` | Architecture + commands for the live `poc/` system and the retired `apps/` stack |
| `poc/README.md` | `poc/` quick start, architecture, deployment |
| `poc/PLAN.md` | Full pivot rationale — why `apps/` was scrapped, design decisions, as-built corrections |
| `AGENTS.md` | Coding rules for `poc/` (current) and `apps/` (retired) |
| `docs/data-flow.md`, `docs/rbac.md`, `docs/runbook.md` | Live `poc/` flow/access/runbook, with the retired Phase 0/1 design kept below each for context |
| `artifacts/` | Original LLD/E2E-deck design docs — historical/aspirational, never built |
| `tasks_sanjay.md` | Companion to the retired 2-week delivery plan — stale, not updated |
