# JobHubNG — Task List

**Updated:** 2026-09-22

**Supersedes the 2-week Spring Boot/Flowable/Kafka delivery plan this file used to track**
(dated 2026-09-11, against the LLD/E2E-deck architecture, with Madhu as product owner and
Codex as implementation accelerator). That plan and the stack it targeted were abandoned on
2026-09-16 for `poc/` — a minimal Python pipeline (scraper → SQLite → Flask+TS web app →
WhatsApp alerts) that already runs, live, entirely on Raspberry Pi hardware (pi05/pi09; a
third host, harita, was removed from the loop on 2026-09-22 — see T7 below). See
`CLAUDE.md` for the full architecture and `poc/PLAN.md` for the pivot rationale.
`tasks_sanjay.md` was a companion to the same retired plan and is equally stale — not
updated here.

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
| Automated scheduling | Done | systemd timer on pi09 (6h, self-orchestrating), EverJobs as a systemd service on pi05 |
| Dockerized web deployment | Done | `jobhub-web` container serves `jobhubs.aavartlabs.com` via the existing Cloudflare Tunnel |

## Open items (as of 2026-09-22 operational check)

| ID | Item | Status | Notes |
| --- | --- | --- | --- |
| T1 | WhatsApp gateway reported "sent" without confirming actual delivery | **Fixed 2026-09-22** | `/send` now waits for baileys' `SERVER_ACK` (`ack-tracker.js`) before reporting success — confirms WhatsApp's servers got the message, not that the recipient's device rendered it. That surfaced a deeper issue: all 3 registered numbers started showing "Waiting for this message" (a stuck-decrypt state), which persisted even after adding a proper `getMessage` handler (`sent-message-cache.js`, needed regardless — the installed baileys' default silently drops WhatsApp's retry-receipt protocol). Root cause was a stale linked-device session (6 days, 39+ reconnects, never re-paired). Fixed by logging out and re-pairing fresh; verified live on all 3 numbers post-repair. |
| T2 | A failed alert send is never retried | Open | `run_alerts.py` only ever considers job ids that were genuinely new in *that* pipeline run (`matcher.find_matches(conn, new_ids)`); once a job ages out of "new," a prior `FAILED` row for it is never reconsidered, and `Notifier.send()`'s existing-row check skips retrying regardless of status anyway. Was low-stakes when sends rarely failed; more consequential now that delivery confirmation (T1) means genuine failures actually get flagged as `FAILED` instead of silently `SENT`. |
| T3 | Pipeline's post-reboot catch-up run fails instantly | **Obsoleted 2026-09-22 by T7** | Was a systemd `Persistent=true` catch-up run dying in <1s right after a **harita** reboot (likely a network-not-ready-at-boot race). Moot now that the pipeline no longer runs on harita at all — pi09 doesn't reboot on this pattern. Left here for history, not re-verified on pi09 specifically. |
| T4 | No CI coverage for `poc/` or `whatsapp-sender` | Open | `.github/workflows/ci.yml` only builds/tests the retired `apps/` stack. `poc/`'s and `poc/scraper/`'s pytest suites and `whatsapp-sender`'s `node --test` suite are verified manually only. |
| T5 | No multi-user auth | Open, by design so far | One shared demo login gates the whole app; no roles, no per-user accounts. Not attempted yet — see `poc/PLAN.md`'s stretch list. |
| T6 | Only one EverJobs site bucket (`google`) exercised | Open | Other buckets/sites were never tried; unknown whether they behave the same way (ignoring query params, same response shape). |
| T7 | Pipeline depended on harita (not 24/7 hardware) as a relay host | **Fixed 2026-09-22** | Originally routed the scrape dump pi05 → harita → pi09 because pi05↔pi09 SSH trust was unconfirmed at design time. Established that trust directly (pi09's key added to pi05's `authorized_keys`; network-level reachability confirmed both directions), rewrote `scripts/run_pipeline.sh` to run on pi09 itself (scrape via SSH, `scp` straight back, load/purge/alert locally), moved the systemd user timer from harita to pi09 (`Linger=yes` there too), and disabled (not deleted) harita's old timer as a rollback path. Verified end-to-end live on pi09, including a real WhatsApp send. The whole pipeline now runs solely on always-on Pi hardware. |

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
- **Moving off Raspberry Pi hardware.** Already largely free, and simpler than before T7:
  every host/port/key/path is env-configured (`poc/.env.example`, `poc/scraper/.env`), and
  `run_pipeline.sh` now just needs an SSH alias to whatever host takes over the `pi05` role
  (it runs on the `pi09`-role host itself) — no third host to reprovision either. The one
  host-specific unknown is whether EverJobs' Playwright/Chromium dependency (confirmed via
  string search in the bundle, never fully characterized) behaves the same on a non-ARM,
  non-Pi host; worth a real check before assuming a lift-and-shift is trivial.

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
