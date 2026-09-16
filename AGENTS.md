# JobHub Codex Rules

The original Low-Level Design under `artifacts/` describes a larger target architecture
(Flowable, a Python agent-runtime, MCP tool boundaries). The current implementation has
diverged from it — see `CLAUDE.md` for the full picture. The rules below describe the
system as it actually exists today; don't assume the LLD's version of a rule still holds.

## Architecture rules

1. Spring Boot owns business logic, APIs, authorization, persistence and audit.
2. There is no Flowable and no BPMN/DMN engine. `workflow/dmn` and `workflow/processes`
   are empty placeholders. `Job.status` is a plain string defaulting to `"DRAFT"` with no
   transition logic anywhere — if you need gating/state transitions, you're building them
   from scratch, not plugging into an existing engine.
3. Agents run in-process inside `platform-api`, not as a separate service. `JobEnrichmentAgent`
   is a normal Spring `@Service` that calls Ollama's `/api/generate` over REST and reads/writes
   repositories directly — there is no agent-runtime process, no OpenAI Agents SDK, and no
   MCP tool boundary. Don't build against an MCP/tool abstraction that isn't there.
4. PostgreSQL is the system of record.
5. Raw ingestion JSON is already immutable today, not a future-phase addition: `jobs_raw`
   (`JobRaw` entity) stores `payload` + `payload_hash` and is never updated after insert.
6. All writes are authorized and audited in principle, but verify before assuming a given
   endpoint is protected — `SecurityConfig` currently `permitAll()`s `/api/v1/admin/**` and
   `/api/v1/jobs/**` at the gateway, so those paths rely solely on method-level
   `@PreAuthorize`. `AuditService` is wired into `AuthService` only; ingestion/enrichment
   writes are not currently audited. Don't extend the permitAll() list further without a
   reason, and prefer adding audit calls to new write paths rather than assuming they exist.
7. Flyway is present as a dependency but **disabled** (`spring.flyway.enabled: false`).
   Schema changes currently happen via Hibernate `ddl-auto: update` against `@Entity`
   classes; `V1__foundation.sql` / `V2__seed_rbac.sql` do not run and are stale. If a task
   requires a real migration path, re-enabling Flyway (and reconciling those SQL files with
   the live schema) is part of the task, not a given.
8. Ingestion idempotency today is a simple existence check
   (`existsBySourceIdAndExternalJobId`) before insert, not a formal
   `JOB_ENRICHMENT:{jobRawId}:{payloadHash}`-style idempotency key. Keep new async writes at
   least this idempotent; a hash-based key is an improvement, not a regression, if you add one.
9. Prefer structured JSON contracts between services (Java DTOs / Jackson here — there's no
   Python side, so no Pydantic).
10. Do not add Kafka, OpenSearch or Kubernetes before the relevant phase acceptance criteria pass.
11. Never commit secrets. `.env` is gitignored; `.env.example` is the template.
12. Never bypass RBAC for convenience — and don't widen `permitAll()` to work around it.

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
