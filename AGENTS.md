# JobHub Codex Rules

You are implementing JobHub according to the approved Low-Level Design.

## Architecture rules

1. Spring Boot owns business logic, APIs, authorization, persistence and audit.
2. Flowable owns business process state, human tasks, retry and deterministic gates.
3. Agents reason; they do not directly access PostgreSQL.
4. Agent tools/MCP are the only agent capability boundary.
5. PostgreSQL is the system of record.
6. Raw ingestion JSON is immutable when Phase 2 adds it.
7. All writes are authorized and audited.
8. Use Flyway for schema changes.
9. Use idempotency for asynchronous operations.
10. Prefer structured JSON contracts between services.
11. Do not add Kafka, OpenSearch or Kubernetes before the relevant phase acceptance criteria pass.
12. Never commit secrets.
13. Never bypass RBAC for convenience.

## Coding loop

Before coding: inspect the relevant module and state a small implementation plan.

During coding: change one vertical slice; reuse existing services; avoid unrelated refactors.

After coding: run formatting/static checks, unit tests, integration tests when available, and the documented smoke test.

## Delivery format for every Codex task

- Files changed
- Design decision
- Tests added/run
- Commands to run
- Acceptance criteria status
- Known limitations
