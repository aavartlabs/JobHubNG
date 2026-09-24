# JobHubNG Access Control

**This repo contains two generations of the project — only `poc/` is live.** See `CLAUDE.md`
for the full picture. The retired Phase 1 Spring Boot RBAC design (`apps/`) is kept further
down for context only — it does not describe the live system.

## Live system (`poc/`): real accounts, ownership instead of roles

There are still no roles or permissions in `poc/` — every account can do exactly the same
things. What exists instead is **per-account ownership**: real self-service accounts, and
alert subscriptions scoped to the account that created them. (The single shared demo login
this section used to describe — `app_users`, `WEB_ADMIN_USERNAME`/`WEB_ADMIN_PASSWORD`,
`scripts/seed_demo_user.py` — was removed along with all three of those things; see
`docs/superpowers/specs/2026-09-22-user-accounts-auth-design.md`.)

Identity lives in a separate service, `poc/auth-service/` (Node + Better Auth, own
`auth.db`), reached only through Flask's `/auth/*` reverse proxy. Flask issues no session
cookie of its own: `poc/jobhub_poc/webapp/auth.py`'s `load_current_user` resolves the
browser's Better Auth cookie against that service on each request (and makes **no** outbound
call at all when the cookie is absent, so anonymous browsing doesn't depend on it being up).

Two things must both be true for `login_required` to let a request through — a session
exists, **and** its user has `emailVerified` and `telegramVerified` both set (it was
`phoneNumberVerified`, a WhatsApp OTP, until 2026-09-24). A session
missing either is redirected to `/verify`, not to `/login`. This check in Flask is the only
verification gate; the auth-service deliberately lets an unverified user sign in, so that
someone who loses their session mid-verification can get back in to finish it.

| Endpoint | Requires account | Notes |
|---|---:|---|
| `GET /jobs` | No | public |
| `GET /api/jobs` | No | public JSON |
| `GET`/`POST /alerts/register` | Yes | stamps `owner_auth_user_id` with the caller's id |
| `GET /alerts` | Yes | lists only the caller's own subscriptions |
| `POST /alerts/<id>/deactivate` | Yes | scoped to `id AND owner_auth_user_id`, so another user's row can't be touched by guessing an id |
| `GET /login`, `/register`, `/verify` | No | the auth boundary itself |
| `POST /logout` | No | POST-only, so a third-party page can't clear a session with an `<img>` tag |
| `/auth/*` | No | byte-level passthrough to the auth-service, which does its own checks |

Ownership is enforced in SQL, not just in the UI — every alert query carries
`owner_auth_user_id = ?`. There is still no admin/seeker/recruiter distinction and no
endpoint more privileged than another.

## Retired: Phase 1 RBAC (`apps/`, Spring Boot, not live)

### Roles

JOB_SEEKER, STUDENT, PROFESSIONAL, RECRUITER, EMPLOYER, ADMIN.

### Enforcement

- JWT carried role and permission claims for UI context.
- Spring Security authenticated every protected request.
- `@PreAuthorize` protected privileged endpoints.
- Frontend menu hiding was convenience only; it was not the security boundary.
- Every write path was designed to emit an audit record.
- Tenant ID was present in the user model and audit/outbox model for future tenant isolation.

### Demo endpoint matrix

| Endpoint | Public | Protected | Admin only |
|---|---:|---:|---:|
| GET /api/v1/public/status | Yes | No | No |
| POST /api/v1/auth/demo-login | Yes | No | No |
| GET /api/v1/auth/me | No | Yes | No |
| GET /api/v1/platform/me | No | Yes | No |
| GET /api/v1/admin/dataflow | No | Yes | Yes |

Note (also called out in `CLAUDE.md`): `SecurityConfig` `permitAll()`'d `/api/v1/jobs/**`
and `/api/v1/admin/**` at the gateway, so the "Admin only" column above relied solely on
method-level `@PreAuthorize`, not the security filter chain, at the path-prefix level.
