# Phase 1 RBAC

## Roles

JOB_SEEKER, STUDENT, PROFESSIONAL, RECRUITER, EMPLOYER, ADMIN.

## Enforcement

- JWT carries role and permission claims for UI context.
- Spring Security authenticates every protected request.
- `@PreAuthorize` protects privileged endpoints.
- Frontend menu hiding is convenience only; it is not the security boundary.
- Every write path is designed to emit an audit record.
- Tenant ID is present in the user model and audit/outbox model for future tenant isolation.

## Demo endpoint matrix

| Endpoint | Public | Protected | Admin only |
|---|---:|---:|---:|
| GET /api/v1/public/status | Yes | No | No |
| POST /api/v1/auth/demo-login | Yes | No | No |
| GET /api/v1/auth/me | No | Yes | No |
| GET /api/v1/platform/me | No | Yes | No |
| GET /api/v1/admin/dataflow | No | Yes | Yes |
