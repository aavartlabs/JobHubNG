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
| Scraper (pi05) | Done | `dump_jobs.py` against live EverJobs; as of 2026-09-22, 5 site buckets (`google,naukri,linkedin,indeed,glassdoor`), client-side filter/cap by `SEARCH_TERMS` |
| Loader + purge (pi09) | Done | dedupe/upsert, `first_seen_at`-only freshness, 15-day purge window |
| Web app (pi09, Docker) | Done | Flask + JSON API + TS frontend; `/jobs`/`/api/jobs` public as of 2026-09-22, `/alerts/*` gated |
| Alert registration + matching | Done | keyword substring match on newly-inserted jobs only, owner-scoped as of 2026-09-22 (T5) |
| WhatsApp delivery | Done | `whatsapp-sender/` (baileys), real number paired, delivery-confirmed (see below) |
| Automated scheduling | Done | systemd timer on pi09 (6h, self-orchestrating), EverJobs as a systemd service on pi05 |
| Dockerized web deployment | Done | `jobhub-web` container serves `jobhubs.aavartlabs.com` via the existing Cloudflare Tunnel |

## Open items (as of 2026-09-22 operational check)

| ID | Item | Status | Notes |
| --- | --- | --- | --- |
| T1 | WhatsApp gateway reported "sent" without confirming actual delivery | **Fixed 2026-09-22** | `/send` now waits for baileys' `SERVER_ACK` (`ack-tracker.js`) before reporting success — confirms WhatsApp's servers got the message, not that the recipient's device rendered it. That surfaced a deeper issue: all 3 registered numbers started showing "Waiting for this message" (a stuck-decrypt state), which persisted even after adding a proper `getMessage` handler (`sent-message-cache.js`, needed regardless — the installed baileys' default silently drops WhatsApp's retry-receipt protocol). Root cause was a stale linked-device session (6 days, 39+ reconnects, never re-paired). Fixed by logging out and re-pairing fresh; verified live on all 3 numbers post-repair. |
| T2 | A failed alert send is never retried | **Open, now confirmed costly** | `run_alerts.py` only ever considers job ids that were genuinely new in *that* pipeline run; once a job ages out of "new," a prior `FAILED` row for it is never reconsidered, and `Notifier.send()`'s existing-row check skips retrying regardless of status anyway. Was theoretical; **confirmed real on 2026-09-22** by T6's site-bucket widening — a 119-alert burst (from the one-time 1003-new-jobs backlog) produced 56 genuine `FAILED` sends (42%) that will never be retried. Explicitly left as-is by decision, since this run was a one-time backlog spike — but the underlying gap is now demonstrated at real scale, not hypothetical, and is the natural next fix if alert volume grows or bursts again. |
| T3 | Pipeline's post-reboot catch-up run fails instantly | **Obsoleted 2026-09-22 by T7** | Was a systemd `Persistent=true` catch-up run dying in <1s right after a **harita** reboot (likely a network-not-ready-at-boot race). Moot now that the pipeline no longer runs on harita at all — pi09 doesn't reboot on this pattern. Left here for history, not re-verified on pi09 specifically. |
| T4 | No CI coverage for `poc/` or `whatsapp-sender` | Open | `.github/workflows/ci.yml` only builds/tests the retired `apps/` stack. `poc/`'s and `poc/scraper/`'s pytest suites and `whatsapp-sender`'s `node --test` suite are verified manually only. |
| T5 | No multi-user auth | **Built 2026-09-22, not yet deployed** | Real self-service accounts shipped (`poc/auth-service/`, Better Auth — email+password+mobile, both OTP-verified; `alert_subscriptions.owner_auth_user_id`). Full design rationale: `docs/superpowers/specs/2026-09-22-user-accounts-auth-design.md`. Code is committed and pushed, but the actual pi09 deployment (DB migration, container rebuild) hasn't happened yet — blocked on setting up a real Resend account + `aavartlabs.com` subdomain DNS (see that spec's "Open items"). See `docs/rbac.md` for the live access model once deployed. |
| T6 | Only one EverJobs site bucket (`google`) exercised | **Fixed 2026-09-22** | Discovered site selection is entirely server-side (`DEFAULT_SITE_NAMES` env var on pi05's EverJobs systemd service, comma-separated list) — the client never controlled it. Widened live to `google,naukri,linkedin,indeed,glassdoor` (11 buckets exist total; picked these 5 as the highest-value set — `naukri` for direct relevance to this project's actual India-heavy subscriber base, plus 3 globally-major boards). Also widened `SEARCH_TERMS` (+manager/analyst/consultant/intern/director) and doubled `RESULTS_PER_TERM` (50→100). Verified live: a combined 5-bucket scrape took **44m37s** (vs ~2.5min for one bucket) and surfaced 1003 genuinely-new jobs in one run — `REQUEST_TIMEOUT_SECONDS` raised 240s→600s to accommodate. This was a one-time backlog effect (4 of 5 buckets scraped for the first time); future runs should see much smaller deltas. See T10 for a real consequence this surfaced. |
| T7 | Pipeline depended on harita (not 24/7 hardware) as a relay host | **Fixed 2026-09-22** | Originally routed the scrape dump pi05 → harita → pi09 because pi05↔pi09 SSH trust was unconfirmed at design time. Established that trust directly (pi09's key added to pi05's `authorized_keys`; network-level reachability confirmed both directions), rewrote `scripts/run_pipeline.sh` to run on pi09 itself (scrape via SSH, `scp` straight back, load/purge/alert locally), moved the systemd user timer from harita to pi09 (`Linger=yes` there too), and disabled (not deleted) harita's old timer as a rollback path. Verified end-to-end live on pi09, including a real WhatsApp send. The whole pipeline now runs solely on always-on Pi hardware. |
| T8 | One recipient's WhatsApp alerts still failing (multi-device session) | Open | Subscription 5 (`+917738001833`, "product manager"), job 1148 (`alerts_sent` id 93): 4 real resend attempts on 2026-09-22, all failed with "no delivery confirmation." Debug logs show this contact has 4 linked WhatsApp devices; 2 requested session retries post-repair (handled correctly by the T1 `getMessage` fix), but no `SERVER_ACK` ever arrived, even after raising `ACK_TIMEOUT_MS` to 45s and watching the full exchange — it went quiet after ~2s and never resumed. Root cause not established (would need deeper WhatsApp protocol knowledge or info about that contact's device setup). `ACK_TIMEOUT_MS` raised from 12s→45s (and the Python `WhatsAppNotifier` default from 20s→55s to match) as a general improvement for multi-device recipients, but this alone did not resolve this specific case. Left as `FAILED`, not retried further — revisit later, possibly after the recipient's devices resync on their own. |
| T9 | New accounts feature (T5) not yet deployed to pi09 | Open | See T5. Deployment plan lives in `/home/sanjayu/.claude/plans/let-us-our-next-twinkly-raccoon.md`'s "Deployment (pi09)" section — backup DB, sync files, run the schema migration, rebuild `web`+`auth-service`+`whatsapp` containers, verify live. Blocked on a real Resend API key + verified sending domain. |
| T10 | `run_alerts.py` has no rate-limit awareness of WhatsApp's own throttling, confirmed costly at real scale | Open | Surfaced by T6's widening: a single pipeline run with 119 alert matches (sequential, one HTTP POST per match, no pacing) produced a 42% failure rate (56/134 in the affected window) against the `whatsapp-sender` gateway — the session visibly struggled under the burst (`docker logs jobhub-whatsapp` showed rapid session churn during the run), though it recovered and stayed healthy afterward. Already named in "If/when this needs to scale" below as a known seam; this is the first time it's actually manifested with real numbers. Fixing T2 (retry) would recover the 56 drops after the fact; adding pacing/backoff to `run_alerts.py`'s send loop would prevent the burst-induced failures in the first place — the latter is the more direct fix for *this* specific failure mode. |

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
  WhatsApp's own throttling. **No longer hypothetical** — see T10: a 119-alert burst on
  2026-09-22 (triggered by T6's site-bucket widening) produced a 42% failure rate. T2 (no
  retry) gets more expensive as subscriber/alert count grows, since more sends means more
  chances for a transient failure to permanently drop an alert. Fixing T2 and/or adding
  pacing to the send loop are the natural next steps before pushing alert volume higher
  again.
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
