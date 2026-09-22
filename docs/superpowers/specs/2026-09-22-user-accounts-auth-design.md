# JobHubNG — Real User Accounts (Auth + Alert Ownership)

**Date:** 2026-09-22
**Status:** Approved for implementation planning
**Supersedes:** the single shared demo login (`app_users`, one shared password,
`login_required` on every route) described in `docs/rbac.md`'s "Live system" section —
this spec replaces that.

## Problem

`poc/`'s web app currently has one shared login (`WEB_ADMIN_USERNAME`/`WEB_ADMIN_PASSWORD`,
seeded once via `scripts/seed_demo_user.py`). Anyone with those credentials can see and
modify every registered alert subscription — there's no real ownership.
`alert_subscriptions.created_by_user_id` exists in the schema but isn't used for access
control.

The actual requirement: open self-service registration (anyone with a valid email and
mobile number), where each user manages their own job-search alert preferences, and — as a
stated future direction, not this spec — eventually applies to jobs through the portal, with
their own stored resume/application history.

## Goals (this spec)

- Real, self-service user accounts: email + password + mobile number, both email and mobile
  verified before the account is usable.
- Self-hosted, not a third-party hosted identity service (ruled out Supabase for this
  reason).
- Lightweight enough to run alongside the existing containers on pi09's Raspberry Pi
  hardware (ruled out Ory Kratos — production wants Postgres/MySQL, not SQLite, meaning a
  whole new DB service; ruled out SuperTokens — its self-hosted core is JVM-based, the same
  resource class as Keycloak, the thing being avoided in the first place).
- `alert_subscriptions` becomes owned per-account: one verified account can have several
  (title/location keyword) subscriptions.
- Job search/browsing (`/jobs`, `/api/jobs`) stays public — no login required to browse.

## Non-goals (this spec)

- Resume storage, job application submission/tracking, duplicate-submission warnings,
  match-quality/rejection-likelihood advice. Real, named future work (see "Future" below),
  but separate sub-projects with their own design needs — not designed here.
- Migrating the 4 existing real alert subscriptions (ids 2/5/6/7) to real ownership. They
  keep running as unowned/legacy rows (see "Migration" below).
- Widening EverJobs' scrape coverage (`SEARCH_TERMS`, site buckets) — an explicitly
  separate, unrelated follow-up task.
- Social login (Google/etc.) — explicitly ruled out in favor of self-hosted email+mobile.
- Roles/admin distinctions among accounts — every verified account has the same
  capabilities: browse jobs, manage their own alerts.

## Approach

**Better Auth**, run as a new companion Node.js service (`poc/auth-service/`), matching the
existing pattern of `poc/whatsapp-sender/` — a small, focused Node service alongside the
Flask app, not embedded in it (Better Auth is a TypeScript library; Flask is Python, so it
cannot run in-process).

Alternatives considered and rejected:

| Option | Why not |
| --- | --- |
| Supabase Auth (hosted) | Third-party hosted dependency — self-hosted was the explicit ask. |
| Ory Kratos | Genuinely lightweight (single Go binary) and battle-tested, but production deployments require Postgres/MySQL/CockroachDB — SQLite is dev/test-only for Kratos. A new DB service conflicts with this stack's SQLite-only, minimal-footprint direction. |
| SuperTokens | Self-hosted core is JVM-based (Java) — same resource class as Keycloak, the thing being avoided in the first place. |
| Hand-rolled (extend `app_users` directly) | Zero new dependencies, but security-sensitive flows (password reset, verification tokens, session fixation) are exactly what a maintained auth library exists to get right — "our own authentication service" implies a real library, not ad hoc code. |

Better Auth fits because it has a genuine, documented-production-ready SQLite adapter (via
Kysely + `better-sqlite3`); its `phoneNumber` plugin exposes a `sendOTP(phone, code)` hook we
fully control — so mobile verification routes through the WhatsApp gateway already built and
fixed this session, not a new paid SMS provider; and its `emailOTP` plugin
(`overrideDefaultEmailVerification: true`) gives email verification the same 6-digit-code UX
as the WhatsApp OTP, rather than a clickable link.

## Architecture

```
Browser
  |
  v
pi09: jobhub-web (Flask) -- the ONLY public entrypoint; the Cloudflare Tunnel's ingress
  |                          is fixed to this container (confirmed earlier this session) --
  |                          no way to expose a second public route for the auth service.
  |
  +--> /jobs, /api/jobs                    (existing, unchanged, public)
  +--> /alerts/*                           (existing, now owner-scoped)
  +--> /auth/*  --(internal Docker network proxy)-->  jobhub-auth (new)
                                                          Better Auth (Node)
                                                          own SQLite file:
                                                          auth.db (separate
                                                          from jobhub.db)
                                                               |
                                                               +--> sendOTP (mobile)
                                                               |      --> whatsapp-sender:3100/send
                                                               |          (existing gateway, unchanged)
                                                               |
                                                               +--> sendVerificationOTP (email)
                                                                      --> a transactional email API
                                                                          (Resend/Mailgun free tier --
                                                                          new, small dependency; the
                                                                          one piece of this design
                                                                          that isn't fully
                                                                          self-hosted, since
                                                                          self-hosting real SMTP
                                                                          deliverability is a much
                                                                          heavier lift than anything
                                                                          else here)
```

Flask reverse-proxies `/auth/*` to `jobhub-auth` over the internal `jobhub` Docker network
(container-to-container, e.g. `http://jobhub-auth:4000/*`), relaying the request/response
including cookies. This keeps a single public origin — no CORS complexity, cookies work
normally. **Flask does not issue its own auth session cookie anymore** — the browser holds
the cookie Better Auth set (via the proxy); Flask only ever verifies it.

## Data flow

**Registration:**
1. `POST /auth/register {email, password, mobile}` (proxied to `jobhub-auth`).
2. `jobhub-auth` creates the Better Auth user (`emailVerified: false`), triggers:
   - `emailOTP`'s `sendVerificationOTP` (type `email-verification`) → the email API.
   - `phoneNumber`'s `sendOTP` → `whatsapp-sender:3100/send`.
3. Account exists but is not usable — a custom `before` hook on sign-in refuses to issue a
   session unless both `emailVerified` and `phoneNumberVerified` are true.
4. User submits both codes (either order): `emailOTP.verifyEmail(code)`,
   `phoneNumber.verify(code)`.
5. Once both flags are true, normal `email+password` sign-in issues a session cookie.

**Every request to an account-gated route** (`/alerts/*` today): Flask's `login_required`
calls `jobhub-auth`'s `get-session` endpoint (forwarding the browser's session cookie)
instead of checking its own session store. A valid response gives the Better Auth user id;
Flask uses that in place of today's `session["user_id"]`.

## Schema changes

- `alert_subscriptions` gains `owner_auth_user_id TEXT` (nullable) — the Better Auth user's
  id. Not a real foreign key: it lives in a different SQLite file/service, so this is an
  opaque string match, not a `REFERENCES` constraint.
- `app_users` (the old shared-login table) is retired outright — dropped from `schema.sql`,
  not kept alongside.
- `/alerts/register` and any subscription-listing view become owner-scoped: a user only
  sees/edits rows where `owner_auth_user_id` matches their own id.

## Migration

The 4 existing real subscriptions (ids 2, 5, 6, 7 — phone numbers `+919902065845`,
`+917738001833` ×2, `+919448928797`) predate any account. They keep `owner_auth_user_id =
NULL` and keep firing through the pipeline exactly as today — the matcher/notifier path only
cares about `is_active` + keyword match, never ownership. No forced migration. A "claim your
existing alert" flow (match by verified phone number) is reasonable future work, not part of
this spec.

## Error handling

- OTP expiry/resend: Better Auth's `expiresIn`/`allowedAttempts` config (both plugins).
- A failed `sendOTP` call to `whatsapp-sender` (a real, demonstrated risk this session — see
  `tasks_all.md`'s T8) must surface as a clear "couldn't send your verification code, try
  again" in the registration UI, not a silent stuck state.
- A failed email-send call gets the same treatment.

## Testing

- `poc/auth-service/`: `node --test` covering the custom dual-verification sign-in hook and
  the `sendOTP`/`sendVerificationOTP` wiring (mocked outbound HTTP calls to the WhatsApp
  gateway and email API) — same style as `poc/whatsapp-sender/`'s existing tests.
- Flask side: extend the existing `poc/tests/test_webapp_auth.py` pattern, mocking the
  internal `get-session` proxy call the same way `WhatsAppNotifier`'s tests already mock
  outbound HTTP (`requests_mock`).
- Live verification: register a real test account end-to-end (real WhatsApp OTP, real email
  OTP) before considering this done — consistent with how the rest of `poc/` has been
  verified live, not just unit-tested.

## Future (not this spec)

Named so the design's extensibility claim (identity lives in its own service; app data just
references an opaque user id) has something concrete to point at — none of this is designed
here:
- Resume storage.
- Job application submission and tracking (with a timeline).
- Duplicate-submission warnings.
- Match-quality / likely-rejection advice on jobs.

Each of these is its own sub-project when it comes up, with its own brainstorm/spec/plan
cycle.
