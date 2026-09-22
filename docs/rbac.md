# JobHubNG Access Control

**This repo contains two generations of the project — only `poc/` is live.** See `CLAUDE.md`
for the full picture. The retired Phase 1 Spring Boot RBAC design (`apps/`) is kept further
down for context only — it does not describe the live system.

## Live system (`poc/`): one shared login, no RBAC

There are no roles, permissions, or per-user accounts in `poc/`. `poc/jobhub_poc/webapp/auth.py`
gates the entire app behind a single shared demo login: one row in the `app_users` table,
seeded by `scripts/seed_demo_user.py` from `WEB_ADMIN_USERNAME`/`WEB_ADMIN_PASSWORD`, checked
via a Flask session and a `login_required` decorator applied uniformly to every blueprint
(`jobs`, `alerts`, `api`). Anyone with the shared credentials has full access to everything —
there is no admin/seeker/recruiter distinction, and no endpoint is more privileged than any
other once logged in.

| Endpoint | Requires login | Notes |
|---|---:|---|
| `GET /jobs` | Yes | redirects to `/login` if unauthenticated |
| `GET /api/jobs` | Yes | JSON, same login gate as the page |
| `GET`/`POST /alerts/register` | Yes | any logged-in session can register any phone number |
| `GET`/`POST /login`, `GET /logout` | No | the auth boundary itself |

Real multi-user account management does not exist and would need to be built from scratch —
see `poc/PLAN.md`'s stretch section ("multi-user account management. Still not done").

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
