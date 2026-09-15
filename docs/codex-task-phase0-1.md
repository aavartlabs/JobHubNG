# Codex Task Pack — Phase 0 + Phase 1

## Task 1: Run the foundation

Read `AGENTS.md`. Start PostgreSQL, run migrations, start Spring Boot, verify actuator health.

Acceptance: API starts and all V1/V2 migrations apply.

## Task 2: Verify demo identity

Call `/api/v1/auth/demo-login` for each persona. Store the token. Call `/api/v1/auth/me`.

Acceptance: role and permission claims match the seeded RBAC model.

## Task 3: Verify RBAC

Call `/api/v1/admin/dataflow` with an admin token and with a seeker token.

Acceptance: admin receives 200; seeker receives 403.

## Task 4: Verify data flow

After one login, query the database:

```sql
select * from audit_events order by created_at desc limit 5;
select * from outbox_events order by created_at desc limit 5;
```

Acceptance: a USER_LOGIN audit event and corresponding outbox event exist; the publisher eventually marks the outbox row PUBLISHED.
