# Database

Flyway migrations live under `apps/platform-api/src/main/resources/db/migration`.

Phase 0/1 schema:
- tenants
- users
- roles
- permissions
- user_roles
- role_permissions
- audit_events
- outbox_events

Phase 2 adds the JobHub job/source/raw ingestion model.
