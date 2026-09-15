# JobHub Phase 0 + Phase 1 Data Flow

## Implemented flow

```text
Browser
  |
  | POST /api/v1/auth/demo-login
  v
Spring Boot AuthController
  |
  v
AuthService
  |
  +--> PostgreSQL users -> roles -> permissions -> tenant
  |
  +--> JWT issued (roles + permissions + tenant)
  |
  +--> AuditOutboxService [single DB transaction]
          |
          +--> audit_events
          |
          +--> outbox_events [PENDING]
                              |
                              v
                        OutboxPublisher
                              |
                              v
                       outbox_events [PUBLISHED]
```

## Why this is the Phase 0/1 data flow

The LLD requires durable business state in PostgreSQL, backend-enforced RBAC, auditability and idempotent asynchronous/event boundaries. The login path exercises these boundaries without pretending that job ingestion has already been implemented.

## Phase 2 extension

```text
Job Source
 -> Spring Boot Connector
 -> jobs_raw (immutable JSONB)
 -> outbox JOB_RECEIVED
 -> Flowable JobEnrichmentProcess
 -> Agent Runtime / OpenAI Agents SDK
 -> structured JobEnrichmentResult
 -> Flowable DMN
 -> canonical jobs OR human review
 -> embedding
 -> search
```

The exact job enrichment sequence is defined in the approved LLD; this repository intentionally stops before Phase 2.
