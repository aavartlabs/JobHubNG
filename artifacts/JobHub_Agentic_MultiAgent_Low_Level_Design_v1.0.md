JOBHUB
Agentic / Multi-Agent Job Intelligence Platform
Low-Level Design and Codex Implementation Guide
Version 1.0  |  September 2026  |  Implementation-ready baseline
Core rule: Agents reason and recommend; tools perform actions; Spring Boot owns business logic and authorization; Flowable owns deterministic workflow and approvals; PostgreSQL remains the system of record.

## 1. Document Control

## 2. How to Use This Design
This document is intentionally written as an implementation contract. A junior developer should be able to create the repository, run the local environment, implement one module at a time, and use the acceptance criteria to verify the result without inventing missing business rules.
- Build only the components described in the current phase. Do not introduce Kafka, OpenSearch, Kubernetes, or additional agent frameworks unless the phase explicitly calls for them.
- Keep all durable business state in PostgreSQL. Agent sessions and traces are operational state; they must not become the canonical source of jobs, users, applications, or permissions.
- For every feature, implement the API contract, service logic, authorization, persistence, audit event, tests, and UI state together where practical.
- Use Codex as a coding accelerator, not as an architecture authority. The developer must compare generated code with this document and the Definition of Done.
- Never make an LLM prompt the only enforcement point for authorization, compliance, financial actions, publication, candidate data access, or destructive operations.

## 3. Table of Contents
4. Product and System Scope
5. Architectural Principles
6. Runtime Components and Responsibilities
7. Repository and Module Layout
8. Environment and Installation
9. Configuration Management
10. Database Low-Level Design
11. Spring Boot Low-Level Design
12. OpenAI Agents SDK Runtime Design
13. Agent Catalog and Contracts
14. MCP Tool Layer Design
15. Flowable BPMN/DMN Design
16. End-to-End Job Enrichment Sequence
17. Candidate / Resume / Matching Flows
18. Recruiter and Employer Agent Flows
19. Search and Ranking Design
20. Notification and Market Intelligence Design
21. Security and RBAC
22. Reliability, Idempotency and Error Handling
23. Observability and Audit
24. API Design
25. Frontend Integration Design
26. Testing Strategy
27. Codex Development Workflow
28. Phase-Wise Build Plan
29. Production Deployment
30. Acceptance Criteria and Definition of Done
31. Risks, Trade-offs and Future Extensions
32. Reference Sources

## 4. Product and System Scope

### 4.1 Personas

### 4.2 In Scope
- Multi-source job ingestion and immutable raw storage.
- Deduplication, AI metadata extraction, classification, skill extraction, taxonomy resolution, quality assessment and embeddings.
- Flowable-controlled job enrichment workflow and confidence-based human review.
- Candidate profile and resume intelligence, semantic job matching, skill gap and learning recommendations.
- Career assistant, recruiter copilot, employer job drafting, market intelligence and notification orchestration.
- Role-based access control, tenant boundary enforcement, audit, tracing and operational dashboards.
- Responsive JobHub web portal with persona-specific navigation and access control.

### 4.3 Out of Scope for First MVP
- Fully autonomous hiring decisions.
- Automatic rejection of candidates based solely on model output.
- Autonomous billing changes.
- Automatic taxonomy creation with no review path.
- Large-scale browser automation or unrestricted scraping that bypasses source terms or security controls.
- Kubernetes-first deployment before local and containerized deployment is stable.

## 5. Architectural Principles

## 6. Runtime Components and Responsibilities
OpenAI SDK baseline: The current Agents SDK exposes agents, tools, agents-as-tools, handoffs, guardrails, sessions, MCP integrations and tracing. Its documentation distinguishes manager-style agent-as-tool orchestration from handoffs, which is directly useful for JobHub.

## 7. Repository and Module Layout

```text
jobhub/
  apps/
    web/                         # Next.js portal
    platform-api/                # Java 21 + Spring Boot
    agent-runtime/               # Python + OpenAI Agents SDK
  mcp/
    job-server/
    candidate-server/
    resume-server/
    search-server/
    taxonomy-server/
    workflow-server/
    analytics-server/
    learning-server/
    notification-server/
  workflow/
    bpmn/
    dmn/
  database/
    migrations/
    seed/
    fixtures/
  infra/
    docker/
    observability/
    kubernetes/
  docs/
    architecture/
    agents/
    api/
    runbooks/
  AGENTS.md
  README.md
  docker-compose.yml
```

### 7.1 Spring Package Structure

```text
com.jobhub
  common/
    audit/
    error/
    idempotency/
    security/
    events/
  auth/
  ingestion/
  jobs/
  taxonomy/
  candidates/
  resumes/
  matching/
  applications/
  recruiters/
  employers/
  learning/
  notifications/
  market/
  analytics/
  workflow/
  ai/
```

### 7.2 Agent Runtime Structure

```text
jobhub_agents/
  agents/
    orchestrator.py
    job/
      validation.py
      duplicate.py
      metadata.py
      classification.py
      location.py
      salary.py
      skills.py
      taxonomy.py
      quality.py
      embedding.py
    candidate/
      profile.py
      resume.py
      matching.py
      skill_gap.py
      learning.py
    career/
      coach.py
    recruiter/
      copilot.py
      ranking.py
      interview.py
    employer/
      copilot.py
      job_draft.py
    operations/
      market.py
      notification.py
      data_quality.py
  tools/
  schemas/
  guardrails/
  prompts/
  sessions/
  evaluations/
  tracing/
  main.py
```

## 8. Environment and Installation

### 8.1 Required local software

### 8.2 Agent Runtime Setup

```text
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate

pip install openai-agents
pip install fastapi uvicorn pydantic httpx python-dotenv
pip install mcp
```
Official SDK install: OpenAI documentation currently lists `pip install openai-agents` as the installation path for the Python Agents SDK.

### 8.3 Suggested Python dependency policy

```text
# requirements.txt - pin versions after the first successful build
openai-agents==<qualified-version>
fastapi==<qualified-version>
uvicorn[standard]==<qualified-version>
pydantic==<qualified-version>
httpx==<qualified-version>
python-dotenv==<qualified-version>
# mcp dependency is brought directly or transitively; pin the tested version
```

### 8.4 Spring Boot Dependencies

```text
spring-boot-starter-web
spring-boot-starter-validation
spring-boot-starter-security
spring-boot-starter-oauth2-resource-server
spring-boot-starter-data-jpa
postgresql
flyway-core
flowable-spring-boot-starter
micrometer-registry-prometheus
spring-boot-starter-actuator
# Spring AI MCP server/client starters as qualified for the chosen release
```
Compatibility: Flowable documentation currently states support for Spring Boot 4.x. Lock the exact Spring Boot/Flowable versions as a tested combination instead of independently upgrading either dependency.

### 8.5 Local containers

```text
docker compose up -d postgres redis
# add flowable and redpanda when those phases are implemented
# application services run from IDE during early development
```

## 9. Configuration Management

### 9.1 Environment Variables

```text
# Common
APP_ENV=local
SERVER_PORT=8080

# Database
DB_URL=jdbc:postgresql://localhost:5432/jobhub
DB_USERNAME=jobhub
DB_PASSWORD=<secret>

# Agent runtime
OPENAI_API_KEY=<secret>
OPENAI_MODEL=<qualified-model>
AGENT_SERVICE_URL=http://localhost:8090

# MCP
MCP_JOB_URL=http://localhost:8091
MCP_CANDIDATE_URL=http://localhost:8092
MCP_RESUME_URL=http://localhost:8093
MCP_SEARCH_URL=http://localhost:8094
MCP_TAXONOMY_URL=http://localhost:8095
MCP_WORKFLOW_URL=http://localhost:8096

# Observability
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

### 9.2 Configuration Rules
- Commit `.env.example`; never commit `.env` or real secrets.
- Fail fast when required secrets are missing in non-test environments.
- External URLs, feature flags, model names and thresholds must be configuration properties, not literals buried in business logic.
- Keep agent prompt versions, taxonomy version and ranking formula version in application configuration or metadata tables so an output is reproducible.
- Do not expose internal MCP endpoints directly to the public browser.

## 10. Database Low-Level Design

### 10.1 Schemas

### 10.2 Core tables

### 10.3 DDL - jobs_raw

```text
CREATE TABLE jobhub.jobs_raw (
    id                BIGSERIAL PRIMARY KEY,
    source_id         BIGINT NOT NULL,
    external_job_id   VARCHAR(500),
    source_url        TEXT,
    payload           JSONB NOT NULL,
    payload_hash      VARCHAR(128) NOT NULL,
    fetched_at        TIMESTAMPTZ NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_id, external_job_id, payload_hash)
);
CREATE INDEX idx_jobs_raw_source_fetched
    ON jobhub.jobs_raw(source_id, fetched_at DESC);
```

### 10.4 DDL - canonical jobs

```text
CREATE TABLE jobhub.jobs (
    id                       BIGSERIAL PRIMARY KEY,
    canonical_title          VARCHAR(500) NOT NULL,
    normalized_description   TEXT NOT NULL,
    company_id               BIGINT,
    status                   VARCHAR(40) NOT NULL,
    country_code             VARCHAR(10),
    city                     VARCHAR(200),
    published_at             TIMESTAMPTZ,
    expires_at               TIMESTAMPTZ,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    version                  BIGINT NOT NULL DEFAULT 0
);
CREATE INDEX idx_jobs_status_published
    ON jobhub.jobs(status, published_at DESC);
```

### 10.5 DDL - AI processing

```text
CREATE TABLE jobhub_ai.ai_processing_runs (
    id                   BIGSERIAL PRIMARY KEY,
    entity_type          VARCHAR(50) NOT NULL,
    entity_id            BIGINT NOT NULL,
    workflow_instance_id VARCHAR(100),
    agent_name            VARCHAR(200) NOT NULL,
    agent_version         VARCHAR(50) NOT NULL,
    model_name            VARCHAR(100),
    prompt_version        VARCHAR(100),
    input_hash            VARCHAR(128),
    output_json           JSONB,
    confidence            NUMERIC(5,4),
    status                VARCHAR(30) NOT NULL,
    trace_id              VARCHAR(100),
    started_at            TIMESTAMPTZ,
    completed_at          TIMESTAMPTZ,
    error_code            VARCHAR(100),
    error_message         TEXT
);
CREATE INDEX idx_ai_runs_entity ON jobhub_ai.ai_processing_runs(entity_type, entity_id);
CREATE INDEX idx_ai_runs_trace ON jobhub_ai.ai_processing_runs(trace_id);
```

### 10.6 pgvector

```text
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE jobhub.job_embeddings (
    job_id       BIGINT PRIMARY KEY,
    embedding    VECTOR(<MODEL_DIMENSION>),
    model_name   VARCHAR(100) NOT NULL,
    model_version VARCHAR(50),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Add an HNSW or IVFFlat index only after validating the workload.
-- The vector dimension must match the selected embedding model.
```

## 11. Spring Boot Low-Level Design

### 11.1 Layering

```text
Controller
  -> Request DTO validation
  -> Application Service
      -> Authorization / Policy
      -> Domain Service
          -> Repository / External Client / Event Publisher
      -> Audit Event
  -> Response DTO
```

### 11.2 Example job ingestion classes

### 11.3 Transaction boundary
A single ingestion transaction should persist the raw record and outbox event atomically. Agent calls and external HTTP requests must not be held open inside a database transaction. Workflow steps should use references to persisted IDs, then commit before invoking the next asynchronous step.

## 12. OpenAI Agents SDK Runtime Design

### 12.1 Runtime responsibilities
- Create configured agents with stable names and versions.
- Load versioned prompts and structured output schemas.
- Attach approved tools or MCP servers.
- Execute specialist agents using manager-style agents-as-tools when the orchestrator must retain control.
- Use handoffs for conversational specialist ownership, mainly for Career Assistant and similar interactive flows.
- Apply input/output/tool guardrails.
- Emit trace metadata and persist an AI processing record through an application tool/API.
- Return a stable result envelope to Flowable or Spring Boot.

### 12.2 Recommended orchestration pattern
For job enrichment, use a manager/orchestrator agent plus specialist agents exposed as tools. The manager owns the final structured enrichment result. For the Career Assistant, use a top-level assistant that can hand off to resume, matching, skill-gap or market specialists when the specialist should become the active conversational agent. This aligns with the current Agents SDK guidance on agents-as-tools versus handoffs.

```text
from agents import Agent

job_orchestrator = Agent(
    name="Job Enrichment Orchestrator",
    instructions=load_prompt("job/orchestrator.v1"),
    tools=[
        validation_agent.as_tool(),
        duplicate_agent.as_tool(),
        metadata_agent.as_tool(),
        skills_agent.as_tool(),
        taxonomy_agent.as_tool(),
        quality_agent.as_tool(),
    ],
    output_type=JobEnrichmentResult,
)
```

### 12.3 Agent context

```text
class JobHubAgentContext(BaseModel):
    request_id: str
    correlation_id: str
    actor_type: Literal["USER", "WORKFLOW", "SYSTEM"]
    actor_id: str | None
    tenant_id: str | None
    role: str | None
    permissions: list[str]
    workflow_instance_id: str | None
```
Security rule: Context values such as user ID, tenant and permissions must come from a trusted caller. Do not ask the model to invent them.

### 12.4 Structured output contract

```text
class AgentResult(BaseModel):
    status: Literal["SUCCESS", "REVIEW", "FAILED"]
    confidence: float = Field(ge=0.0, le=1.0)
    findings: list[str]
    evidence: list[str]
    recommendations: list[str]
    requires_human_review: bool
    agent_name: str
    agent_version: str
    trace_id: str | None
```

## 13. Agent Catalog and Contracts

### 13.1 Example JobEnrichmentResult

```text
{
  "status": "SUCCESS",
  "confidence": 0.94,
  "duplicate": {"isDuplicate": false, "score": 0.08},
  "metadata": {
    "country": "AE",
    "city": "Dubai",
    "employmentType": "FULL_TIME",
    "workMode": "HYBRID",
    "seniority": "SENIOR",
    "experienceMin": 5,
    "experienceMax": 8
  },
  "skills": [
    {"name": "Java", "importance": "REQUIRED", "confidence": 0.98},
    {"name": "Spring Boot", "importance": "REQUIRED", "confidence": 0.97}
  ],
  "taxonomy": {
    "industry": "TECHNOLOGY",
    "function": "SOFTWARE_DEVELOPMENT"
  },
  "requiresHumanReview": false,
  "agentVersion": "job-enrichment-1.0.0"
}
```

## 14. MCP Tool Layer Design
Model Context Protocol is the boundary through which the agent runtime consumes controlled capabilities. The recommended implementation uses small domain-oriented MCP servers backed by Spring services. Spring AI provides MCP server/client support; the OpenAI Agents SDK supports MCP-backed tools. The public browser should never connect to these internal MCP endpoints.

### 14.1 Tool naming

```text
job.search
job.get
job.findSimilar
candidate.search
candidate.get
resume.get
resume.parse
search.jobsSemantic
taxonomy.resolve
taxonomy.searchSkills
workflow.start
workflow.getStatus
workflow.requestReview
analytics.marketDemand
learning.search
notification.create
```

### 14.2 Tool contract example

```text
{
  "name": "job.search",
  "description": "Search published JobHub jobs using deterministic filters and optional semantic query.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {"type": "string"},
      "location": {"type": "string"},
      "skills": {"type": "array", "items": {"type": "string"}},
      "page": {"type": "integer", "minimum": 0},
      "size": {"type": "integer", "minimum": 1, "maximum": 50}
    },
    "required": []
  }
}
```

### 14.3 Read versus write tools

### 14.4 Tool guardrails
- Validate tool inputs against schema before execution.
- Check actor identity, role, tenant and permission on every write tool.
- Validate output before giving data back to the model.
- Rate-limit expensive or sensitive tools.
- Never return secrets, passwords, internal tokens or raw PII unless the caller is explicitly authorized.
- Log request ID, tool name, actor, target ID, decision and latency.

## 15. Flowable BPMN/DMN Design

### 15.1 Job enrichment BPMN

```text
START_EVENT
  -> receiveJob
  -> validateInput
  -> duplicateCheck
  -> [exclusiveGateway duplicate?]
       yes -> markDuplicate -> END
       no  -> invokeAgentOrchestrator
  -> persistAiResult
  -> confidenceDecision(DMN)
       PUBLISH -> canonicalizeJob -> embedJob -> publishSearch -> END
       REVIEW  -> createHumanReviewTask -> waitForReview
                     -> applyCorrection -> canonicalizeJob -> embedJob -> publishSearch -> END
       REJECT  -> rejectJob -> END
```

### 15.2 Process variables

### 15.3 DMN decision table
Important: Thresholds are examples for MVP. Store them in DMN and configuration so they can be adjusted without changing agent prompts.

## 16. End-to-End Job Enrichment Sequence

### 16.1 Detailed sequence

### 16.2 Sequence diagram

```text
Source -> Ingestion API: POST /internal/v1/ingestion/jobs
Ingestion API -> PostgreSQL: INSERT jobs_raw
Ingestion API -> Outbox: INSERT JOB_RECEIVED
Outbox -> Flowable: start JobEnrichmentProcess(jobRawId)
Flowable -> Agent Runtime: POST /internal/v1/agent-runs/job-enrichment
Agent Runtime -> Validation Agent: validate
Agent Runtime -> Duplicate Agent: check duplicate
Agent Runtime -> Metadata Agent: extract metadata
Agent Runtime -> Skills Agent: extract skills
Agent Runtime -> Taxonomy Agent: resolve taxonomy
Agent Runtime -> Quality Agent: assess quality
Agent Runtime -> Flowable: structured JobEnrichmentResult
Flowable -> DMN: evaluate confidence / quality / duplicate
DMN -> Spring Boot: persist canonical job OR create review task
Spring Boot -> PostgreSQL: jobs + metadata + skills + mappings
Spring Boot -> Embedding service: create embedding
Embedding service -> PostgreSQL: job_embeddings
Spring Boot -> Search: index/searchable state
```

## 17. Candidate / Resume / Matching Flows

### 17.1 Resume upload

```text
Browser
  -> POST /api/v1/resumes
Spring Boot
  -> Object Storage: upload binary
  -> PostgreSQL: resumes(status=PROCESSING)
  -> Flowable: ResumeProcessingProcess
Flowable
  -> Parser/OCR service
  -> Agent Runtime: Resume Agent
Agent Runtime
  -> Skills/Taxonomy tools
  -> returns ResumeExtractionResult
Flowable
  -> PostgreSQL: resume_versions + user_profile draft
  -> Human confirmation task when confidence is low
  -> Embedding
  -> status READY
```

### 17.2 Matching pipeline
Candidate-job matching is a hybrid ranking problem, not a pure LLM problem. First apply deterministic hard filters such as published status, country/work mode and required constraints. Then retrieve semantically similar jobs or candidates with pgvector, calculate feature-level scores, and only use an agent to explain or reason about ambiguous transitions. The result is stored as a reproducible `job_matches` record.

```text
finalScore =
    0.30 * keywordScore +
    0.25 * semanticScore +
    0.15 * skillScore +
    0.10 * experienceScore +
    0.10 * locationScore +
    0.05 * freshnessScore +
    0.05 * preferenceScore
```
Versioning: Store ranking_formula_version with match records. Change the formula through configuration, test it offline, then roll out gradually.

### 17.3 Skill gap
- Build job-required skill set from canonical job skills.
- Build candidate skill set from profile, resume and explicit user input.
- Normalize both through the same skill taxonomy.
- Calculate deterministic gap candidates.
- Use Skill Gap Agent to explain the gap and suggest prioritization.
- Pass gaps to Learning Agent for learning-path recommendations.

## 18. Recruiter and Employer Agent Flows

### 18.1 Recruiter candidate search

```text
Recruiter UI
  -> POST /api/v1/recruiter/candidates/search
Spring Boot
  -> authorization(tenant + recruiter permission)
  -> Candidate Search Service
      -> SQL hard filters
      -> pgvector similarity
      -> feature scoring
  -> Recruiter Copilot (optional explanation)
  -> response with ranked candidates + evidence
```

### 18.2 Recruiter copilot guardrails
- Use job-relevant attributes only.
- Do not expose protected or irrelevant personal attributes for ranking.
- Never produce an autonomous final hiring/rejection decision.
- Candidate contact or status change requires an authorized tool.
- Every recruiter action is audited with recruiter, tenant, candidate, action and timestamp.

### 18.3 Employer job creation

```text
Employer asks: "Create a backend Java role in Dubai."
  -> Employer Copilot drafts title/description/requirements
  -> Job draft tool persists draft
  -> Employer reviews / edits
  -> Submit for publication
  -> Flowable publication workflow
  -> policy validation + approval if required
  -> publish canonical job
```

## 19. Search and Ranking Design

### 19.1 Search request

```text
GET /api/v1/jobs?q=java%20developer&location=Dubai&workMode=HYBRID&size=20&page=0&sort=relevance
```

### 19.2 Search stages
1. Validate query and normalize filters.
1. Apply hard visibility filters: status=PUBLISHED, not expired, tenant/public visibility.
1. Apply structured filters: location, work mode, employment, experience, salary, industry, skill.
1. Run keyword matching.
1. Run semantic vector retrieval when requested or when natural-language intent is detected.
1. Blend scores using versioned ranking configuration.
1. Load small explanation metadata; do not call an LLM for every result.
1. Return results with source attribution and application link.

### 19.3 Natural-language search
Natural-language search can be routed through a lightweight Query Understanding Agent that turns user language into a structured search plan. The agent must return a schema such as `{keywords, locations, skills, seniority, workMode, salary, intent}`. The Search Service executes that plan. This prevents the LLM from becoming the database query engine.

## 20. Notification and Market Intelligence Design

### 20.1 Notification flow

```text
JobPublished
  -> Match Event
  -> Candidate Matching Worker
  -> Notification Policy
      - user opted in?
      - channel allowed?
      - frequency limit?
      - duplicate notification recently?
  -> Notification Agent (message personalization only)
  -> Notification Service
  -> Push / Email / WhatsApp provider
  -> Delivery status event
```

### 20.2 Market intelligence
Numeric analytics should be computed by SQL or an analytics service. The Market Intelligence Agent receives verified metrics and converts them into an explanation, trend summary or career recommendation. This prevents hallucinated numeric market claims.

## 21. Security and RBAC

### 21.1 Security layers

```text
Browser
  -> OAuth2/OIDC login
  -> JWT access token
  -> Spring Security resource server
  -> method/service authorization
  -> tenant filter
  -> domain ownership checks
  -> repository query

Agent
  -> trusted caller context
  -> MCP authentication
  -> same Spring Security / policy layer
  -> tool authorization
  -> domain service
```

### 21.2 Roles and permissions

### 21.3 Tenant isolation
- Every employer-owned entity has tenant_id or a reachable tenant owner.
- Recruiter queries must include tenant restrictions before candidate/job selection.
- An MCP tool must receive trusted tenant context and apply it before retrieving data.
- Tests must include cross-tenant access attempts.
- Never rely on a frontend tenant ID or prompt-provided tenant ID.

### 21.4 Sensitive actions

## 22. Reliability, Idempotency and Error Handling

### 22.1 Idempotency

```text
idempotency_key = "JOB_ENRICHMENT:{jobRawId}:{payloadHash}"

Before running an expensive step:
  1. Check ai_processing_runs / operation table.
  2. If SUCCESS exists for the same input/version, reuse it.
  3. If IN_PROGRESS is stale, mark recoverable and retry.
  4. If FAILED and retryable, schedule bounded retry.
```

### 22.2 Retry matrix

### 22.3 Circuit breakers
- Use timeouts on every external call.
- Use circuit breakers for external providers where supported.
- Prevent cascading failures from agent runtime to the main API.
- Bulk operations should use worker queues and concurrency limits.

## 23. Observability and Audit

### 23.1 Trace model

```text
correlationId
  ├── HTTP request span
  ├── Flowable process span
  ├── agent run span
  │     ├── LLM generation
  │     ├── tool call
  │     ├── handoff / agent-as-tool
  │     └── guardrail
  ├── database span
  └── external provider span
```

### 23.2 Metrics

### 23.3 Audit fields

```text
audit_id
actor_type
actor_id
role
tenant_id
correlation_id
trace_id
action
entity_type
entity_id
before_hash
after_hash
outcome
reason
created_at
```

## 24. API Design

### 24.1 Public / user APIs

### 24.2 Internal APIs

### 24.3 Error response

```text
{
  "timestamp": "2026-09-09T12:00:00Z",
  "status": 400,
  "code": "JOB_INVALID",
  "message": "Job description is required",
  "requestId": "req-123",
  "details": []
}
```
API rule: Never return stack traces, SQL errors, secrets or internal model prompts to the browser.

## 25. Frontend Integration Design

### 25.1 Application areas

### 25.2 UI behavior
- Header and side navigation are rendered from a server-approved role/permission model; frontend routes additionally enforce client UX rules.
- Search filters are query-string driven so results can be bookmarked/shared.
- Long operations show a request status and do not block the browser.
- AI responses stream through SSE where useful; failures fall back to a retry message and request ID.
- Every destructive/high-impact action shows explicit confirmation and the server repeats the authorization check.

## 26. Testing Strategy

### 26.1 Test pyramid

### 26.2 Golden datasets
- At least 500 representative raw jobs for initial extraction tests.
- At least 100 duplicate/non-duplicate pairs.
- At least 200 taxonomy alias cases.
- At least 100 resumes with different layouts.
- At least 100 candidate/job matching scenarios including partial and career-transition cases.
- At least 50 low-confidence cases that must route to human review.

### 26.3 Security tests
- Candidate A cannot read Candidate B private resume.
- Recruiter from Tenant A cannot read Candidate/Job private records from Tenant B.
- Recruiter cannot invoke taxonomy update tool.
- Anonymous user cannot invoke authenticated APIs.
- Agent context cannot override JWT tenant/role.
- User cannot publish an employer job without the required permission/workflow state.

## 27. Codex Development Workflow

### 27.1 AGENTS.md baseline

```text
# JobHub Engineering Rules

1. Java 21 + Spring Boot for business/domain services.
2. Python + OpenAI Agents SDK only for agent runtime.
3. Flowable owns workflow state, human tasks, retries and deterministic gates.
4. Agents never access PostgreSQL directly.
5. Agents use approved tools/MCP only.
6. PostgreSQL is the system of record.
7. Raw ingestion JSON is immutable.
8. All writes are authorized and audited.
9. Use Flyway for schema changes.
10. Use idempotency for async operations.
11. Use structured outputs for agent-to-service contracts.
12. Add unit + integration + evaluation tests with each feature.
13. Prefer existing libraries; do not add a framework without a written reason.
14. Do not introduce Kafka/OpenSearch/Kubernetes until the current phase acceptance criteria pass.
15. Never commit secrets.
16. Never bypass the documented RBAC boundary for convenience.
```

### 27.2 Codex prompt template

```text
You are implementing JobHub according to the approved LLD.

TASK:
<one small vertical slice>

MUST:
- Follow repository AGENTS.md.
- Reuse existing domain models/services where possible.
- Implement API + service + persistence + authorization + audit + tests.
- For agent work, use OpenAI Agents SDK and the specified structured schemas.
- For tool calls, use MCP/approved service tools; never direct SQL from agents.
- For workflow, update BPMN/DMN and add process tests.
- Do not change unrelated modules.

DELIVER:
1. Files changed
2. Design decisions made
3. Tests added
4. Commands to run
5. Acceptance criteria status
6. Known limitations
```

### 27.3 Recommended Codex loop
1. Ask Codex to inspect repository and produce a short implementation plan before coding.
1. Implement one module or vertical slice.
1. Run formatting, static analysis, unit tests and integration tests.
1. Run the golden AI evaluation for the affected agent.
1. Inspect traces for at least three representative agent runs.
1. Run the E2E scenario if the feature crosses workflow/API boundaries.
1. Commit only after all acceptance criteria pass.

## 28. Phase-Wise Build Plan

## 29. Production Deployment

### 29.1 Development topology

```text
Developer machine
  Docker:
    postgres + pgvector
    redis
  IDE:
    Spring Boot API
    Python agent runtime
    Next.js web
  Optional:
    Flowable
    Redpanda
    observability stack
```

### 29.2 Production topology

```text
Internet
  -> Load Balancer / WAF
  -> Next.js
  -> API Gateway / Ingress
      -> Spring Boot API replicas
      -> Agent Runtime replicas
      -> MCP server replicas
      -> Flowable service / workers

Private network
  -> PostgreSQL HA + pgvector
  -> Redis
  -> Kafka/Redpanda (when justified)
  -> Object storage
  -> Observability
  -> Secret manager
```

### 29.3 Kubernetes minimum
- Use separate Deployments for API, agent runtime and each independently scaled MCP server where needed.
- Use ConfigMaps only for non-secret config and Secrets/secret-manager integration for credentials.
- Use readiness/liveness probes.
- Set CPU/memory requests and limits.
- Use Horizontal Pod Autoscaling only after metrics are stable.
- Keep Flowable engine state and PostgreSQL persistent storage outside ephemeral pods.

## 30. Acceptance Criteria and Definition of Done

### 30.1 Agentic job pipeline acceptance
- Given a new raw job, the system persists immutable JSON and creates a single workflow instance.
- The orchestrator returns schema-valid structured output for validation, duplicate, metadata, skills, taxonomy and quality.
- Every agent run is traceable to request ID, workflow ID and agent version.
- Duplicate jobs do not create a second canonical job.
- High-confidence jobs publish only when the DMN gate allows them.
- Low-confidence jobs create a Flowable human task.
- Human correction can resume and complete the workflow.
- Published jobs are searchable and have a valid source/application URL.
- Re-running the same input does not create duplicate canonical jobs or duplicate notifications.

### 30.2 Candidate matching acceptance
- Candidate profile and skills can be parsed from a test resume.
- Match ranking is reproducible from stored feature scores and ranking formula version.
- Candidate sees why a job matched and what skill gaps exist.
- Career Assistant can search jobs and use matching/skill-gap tools.
- No candidate decision is presented as a final hiring decision.

### 30.3 Production readiness gates

## 31. Risks, Trade-offs and Future Extensions

### 31.1 Future extensions
- OpenSearch for high-scale faceted search.
- Kafka/Redpanda for high-volume event distribution.
- Agent evaluation pipelines and automated regression gates.
- Dedicated ranking/ML models for large candidate/job populations.
- Multi-language candidate/resume processing.
- Voice/realtime Career Assistant if product demand justifies it.
- Agent sandboxing for specialized file/repository workflows where needed; keep it isolated from the canonical platform boundary.

## 32. Reference Sources
- OpenAI Agents SDK - overview: https://openai.github.io/openai-agents-python/
- OpenAI Agents SDK - agents, tools, output types and orchestration: https://openai.github.io/openai-agents-python/agents/
- OpenAI Agents SDK - multi-agent orchestration: https://openai.github.io/openai-agents-python/multi_agent/
- OpenAI Agents SDK - handoffs: https://openai.github.io/openai-agents-python/handoffs/
- OpenAI Agents SDK - tracing: https://openai.github.io/openai-agents-python/tracing/
- OpenAI Agents SDK - quickstart: https://openai.github.io/openai-agents-python/quickstart/
- OpenAI Agents SDK - MCP: https://openai.github.io/openai-agents-python/mcp/
- OpenAI Agents SDK - guardrails: https://openai.github.io/openai-agents-python/guardrails/
- Spring AI - MCP overview: https://docs.spring.io/spring-ai/reference/api/mcp/mcp-overview.html
- Flowable - Spring Boot integration: https://www.flowable.com/open-source/docs/bpmn/ch05a-Spring-Boot
- Flowable documentation: https://www.flowable.com/open-source/docs/
- pgvector repository: https://github.com/pgvector/pgvector
Source note: Technology capabilities cited above should be re-checked against the exact versions pinned in the repository before each major upgrade. The design intentionally avoids hard-coding a future package version where compatibility must be qualified in your environment.

## Appendix A - Junior Developer Quick Start Checklist
1. Clone repository and read AGENTS.md.
1. Install JDK 21, Maven, Node LTS, Python 3.12+, Docker.
1. Run PostgreSQL + pgvector container.
1. Run Flyway migrations and seed taxonomy.
1. Start Spring Boot and verify `/actuator/health`.
1. Create Python venv and install `openai-agents` plus agent dependencies.
1. Set OPENAI_API_KEY through local environment only.
1. Start agent runtime and verify a health endpoint.
1. Start MCP Job and Taxonomy servers.
1. Run the single-source ingestion test.
1. Observe `JOB_RECEIVED` and the Flowable process.
1. Run one job through enrichment.
1. Verify AI result in `ai_processing_runs`.
1. Verify DMN publishes a high-confidence job.
1. Force low confidence and verify human review task.
1. Complete review and verify the job becomes published.
1. Verify vector exists and search returns the job.
1. Run the candidate match scenario.
1. Run all tests and inspect agent traces.
1. Only then ask Codex to implement the next vertical slice.

## Tables (source DOCX retains all formatted tables)

### Table 1
| Item | Value |
| --- | --- |
| Document | JobHub Agentic / Multi-Agent Low-Level Design |
| Version | 1.0 |
| Audience | College graduate / junior developer using Codex or a similar coding assistant |
| Primary implementation stack | Next.js/React, Java 21 + Spring Boot, Flowable BPMN/DMN, Python + OpenAI Agents SDK, MCP, PostgreSQL + pgvector |
| Architecture style | Modular monolith first; independently deployable agent runtime; event-driven at scale |
| Primary development goal | Produce a working end-to-end vertical slice before expanding all agents |
| Status | Baseline design for implementation |

### Table 2
| Persona | Primary capabilities | High-risk actions |
| --- | --- | --- |
| Job Seeker | Discover jobs, save, apply, profile, resume, matches, career assistant, learning, notifications | None beyond own data and application actions |
| Student / Fresher | Entry-level search, internships, learning path, career coach, profile | None beyond own data |
| Working Professional | Senior roles, salary/work-mode filters, target roles, market intelligence, resume | None beyond own data |
| Recruiter / Hiring Manager | Candidate search, requisitions, shortlist, applications, interviews, recruiter copilot | Candidate contact, status changes, interview actions |
| Employer / Company Admin | Jobs, candidates, talent pipeline, company profile, analytics, team, billing | Publish jobs, team admin, billing-sensitive actions |
| Platform Admin / Ops | Ingestion, data quality, duplicates, AI review, taxonomy, users, notifications, audit | System configuration, taxonomy, moderation, operational controls |

### Table 3
| ID | Principle |
| --- | --- |
| P1 - Separation of concerns | LLM agents interpret, plan, classify, rank and recommend. Spring services execute business operations. Flowable controls business state. PostgreSQL stores durable state. |
| P2 - Tool mediation | Agents never receive raw DB credentials or direct SQL capabilities. Data and actions are accessed through controlled tools/MCP endpoints. |
| P3 - Deterministic gates | Confidence thresholds, approval requirements, SLAs and retry rules are expressed as code/DMN rather than natural-language instructions. |
| P4 - Least privilege | Each tool has a permission, tenant boundary, input validation and audit trail. |
| P5 - Structured AI output | Every agent that feeds another component emits a schema-validated result with status, confidence, evidence and agent version. |
| P6 - Idempotency | Replayed source events, workflow retries and duplicate user requests must not create duplicate canonical records or side effects. |
| P7 - Human control | Low-confidence or high-impact operations are routed to human tasks in Flowable. |
| P8 - Explainability | Job matches, AI decisions and operational decisions must retain the evidence and version information needed to explain what happened. |
| P9 - Async where slow | OCR, enrichment, embeddings, bulk matching and notifications should run asynchronously. HTTP APIs return job/request IDs for long work. |
| P10 - Start simple | Use PostgreSQL Outbox before Kafka/Redpanda and PostgreSQL + pgvector before OpenSearch. Introduce infrastructure only when metrics justify it. |

### Table 4
| Component | Responsibility |
| --- | --- |
| Next.js Web | Portal, search UX, dashboards, responsive layouts, access-aware navigation. Never contains authoritative authorization. |
| Spring Boot Platform | REST APIs, domain logic, persistence, RBAC, tenant checks, integration, outbox, notification orchestration, audit. |
| Flowable | BPMN process state, service tasks, timers, retries, human tasks, DMN decisions and approval gates. |
| Agent Runtime | Python service using OpenAI Agents SDK. Coordinates specialist agents, calls MCP/function tools, applies agent guardrails, stores/returns structured results. |
| MCP Servers | Expose narrowly-scoped capabilities to agents. Recommended servers: job, candidate, resume, search, taxonomy, workflow, analytics, learning and notification. |
| PostgreSQL + pgvector | System of record for business entities plus embeddings for semantic retrieval. |
| Redis | Short-lived cache, rate limiting and optional session support; not canonical state. |
| Object Storage | Resume/source files and large artifacts; store references and hashes in PostgreSQL. |
| Outbox / Kafka | Reliable event delivery. Outbox first; Redpanda/Kafka when throughput and decoupling requirements justify it. |
| Observability | OpenAI agent tracing plus application traces/metrics/logs using OpenTelemetry, Prometheus/Grafana and structured logging. |

### Table 5
| Tool | Purpose | Minimum baseline |
| --- | --- | --- |
| Git | Source control | Current enterprise-supported version |
| JDK | Spring Boot runtime | Java 21 |
| Maven | Java build | 3.9+ |
| Python | Agent runtime | 3.12+ |
| Node.js | Next.js development | Current LTS |
| Docker Desktop or Podman | Local infrastructure | Current stable |
| PostgreSQL | Primary DB | Supported recent release; pin exact image |
| pgvector | Vector search | Compatible with chosen PostgreSQL image |
| IDE | Development | VS Code / IntelliJ / equivalent |
| Codex | AI-assisted coding | Use current supported client/CLI in your environment |

### Table 6
| Schema | Purpose |
| --- | --- |
| jobhub | Canonical platform/business tables |
| jobhub_taxonomy | Controlled taxonomies, aliases and skills |
| jobhub_ai | AI processing, traces, agent outputs and evaluation data |
| jobhub_user | Users, profiles, preferences, resumes and candidate data |
| jobhub_notification | Notifications and delivery attempts |
| jobhub_analytics | Market snapshots, aggregate analytics and forecasts |
| flowable | Flowable engine tables; managed by Flowable, not by application migrations unless explicitly required |

### Table 7
| Table | Key columns | Purpose |
| --- | --- | --- |
| job_sources | id, code, name, type, status | Connector registry |
| ingestion_runs | id, source_id, started_at, status, counters | Source execution audit |
| jobs_raw | id, source_id, external_job_id, payload JSONB, payload_hash | Immutable source record |
| job_raw_versions | id, job_raw_id, payload JSONB, payload_hash | Optional source history |
| jobs | id, canonical_title, description, company_id, status | Canonical user-visible job |
| job_sources_mapping | job_id, source_id, external_job_id | Maps canonical job to one or more sources |
| job_duplicate_candidates | job_id, candidate_job_id, score, decision | Ambiguous duplicate relationships |
| companies | id, name, normalized_name | Company entity |
| job_metadata | job_id, taxonomy IDs, work mode, salary, experience, confidence | Normalized enrichment |
| job_skills | job_id, skill_id, importance, confidence, evidence | Skill requirements |
| job_embeddings | job_id, vector, model_name, version | Semantic search |
| users | id, email, status, tenant_id | Identity |
| user_profiles | user_id, headline, role, experience, preferences JSONB | Candidate profile |
| user_skills | user_id, skill_id, proficiency, evidence | Candidate skills |
| resumes | id, user_id, object_key, status, hash | Resume artifact metadata |
| resume_versions | id, resume_id, extracted_json, parser_version | Versioned parsing results |
| job_matches | id, user_id, job_id, score components, explanation | Candidate-job ranking |
| saved_jobs | user_id, job_id, created_at | User saves |
| applications | id, user_id, job_id, status, timestamps | Application lifecycle |
| ai_processing_runs | id, entity, agent, model, prompt, output JSON, confidence, trace | AI audit |
| human_review_tasks | id, workflow, entity, reason, payload, decision | Human review |
| outbox_events | id, event_type, aggregate_type, aggregate_id, payload, status | Reliable event delivery |
| notifications | id, user_id, type, channel, status, payload | Notification record |
| notification_attempts | id, notification_id, provider, status, error | Delivery audit |

### Table 8
| Class | Responsibility |
| --- | --- |
| JobSourceConnector | Fetch source records; no DB writes beyond a service callback |
| IngestionService | Normalize connector input, compute hash, persist jobs_raw, create outbox event |
| JobRawRepository | Read/write raw ingestion records |
| JobEnrichmentWorkflowService | Start/restart the Flowable job process |
| JobCanonicalizationService | Persist validated canonical job fields |
| JobSearchService | Apply deterministic filters and vector retrieval |
| JobAuthorizationService | Enforce publication, tenant and ownership rules |
| AuditService | Persist security and business audit events |

### Table 9
| Agent | Responsibility | Input | Primary tools | Direct side effects |
| --- | --- | --- | --- | --- |
| Job Enrichment Orchestrator | Coordinates job analysis; returns JobEnrichmentResult | Job raw ID + policy context | Validation, Duplicate, Metadata, Classification, Location, Skills, Taxonomy, Quality | No direct writes |
| Source Ingestion Agent | Understands source payload shape when deterministic mapping is insufficient | Raw payload | Source mapping tools | No canonical write |
| Validation Agent | Checks job completeness and legitimacy | Normalized draft | Job read tools | No |
| Duplicate Agent | Determines duplicate/related job probability | Job + candidate jobs | Job search/vector tools | No |
| Metadata Agent | Extracts normalized job attributes | Job description | Taxonomy/search tools | No |
| Classification Agent | Maps job to controlled job taxonomy | Job + taxonomy | Taxonomy tools | No |
| Location Agent | Normalizes country/city/work location | Location text | Location/taxonomy tools | No |
| Salary Agent | Normalizes salary expressions | Salary text | Currency/rules tool | No |
| Skills Agent | Extracts required/preferred skills | Description | Skill taxonomy tool | No |
| Taxonomy Agent | Resolves aliases to controlled values | Candidate labels | Taxonomy MCP | No auto taxonomy creation |
| Quality Agent | Checks quality/compliance indicators | Enrichment result | Job/source tools | No |
| Embedding Agent | Requests embedding/index operation | Canonical content | Embedding tool | No direct DB write |
| Candidate Profile Agent | Builds structured candidate profile | User/resume data | Candidate/resume tools | Writes only through tools after policy |
| Resume Agent | Interprets parsed resume content | Parsed resume | Resume tools | Draft only |
| Matching Agent | Explains candidate/job compatibility | Candidate + job features | Search/candidate/job tools | No candidate rejection |
| Skill Gap Agent | Identifies job-relevant missing skills | Candidate + job | Skill tools | No |
| Learning Agent | Builds learning recommendations | Skill gaps | Learning tool | No paid purchase |
| Career Assistant | Conversational orchestration across career domains | User request + profile | Specialist agents/tools | Sensitive actions require approval |
| Recruiter Copilot | Assists search/ranking and recruitment workflow | Recruiter task | Candidate/job/application tools | No autonomous hiring decision |
| Employer Copilot | Drafts jobs and employer actions | Employer request | Job/company tools | Publishing requires workflow/approval |
| Market Intelligence Agent | Explains analytical results | Calculated metrics | Analytics tool | Cannot invent metrics |
| Notification Agent | Chooses audience/message/channel within policy | Match event/preferences | Notification tool | Provider credentials hidden |
| Admin/Data Quality Agent | Diagnoses ingestion and data issues | Operational data | Metrics/log/source tools | High-risk changes require approval |

### Table 10
| Category | Examples | Default policy |
| --- | --- | --- |
| Read-only | job.search, job.get, taxonomy.resolve, analytics.marketDemand | Allowed when caller has read permission |
| Draft | create_job_draft, generate_resume_draft | Allowed; mark output as draft |
| Sensitive write | publish_job, contact_candidate, reject_application, billing change | Requires permission + policy + workflow/approval when configured |
| Destructive | delete user, purge source data | Admin-only + explicit confirmation + audit |

### Table 11
| Variable | Type | Owner | Purpose |
| --- | --- | --- | --- |
| jobRawId | Long | Platform | Input reference |
| jobId | Long | Platform | Canonical job reference after creation |
| workflowInstanceId | String | Flowable | Correlation |
| duplicateScore | Decimal | Agent/platform | Duplicate signal |
| duplicateDecision | String | DMN | DUPLICATE or NOT_DUPLICATE |
| aiConfidence | Decimal | Agent result | Confidence score |
| qualityStatus | String | Quality agent | PASS/FAIL/REVIEW |
| reviewRequired | Boolean | DMN | Human task gate |
| reviewReason | String | Platform | Why review is needed |
| taxonomyVersion | String | Taxonomy service | Reproducibility |
| embeddingRequired | Boolean | Workflow | Embedding branch control |

### Table 12
| Duplicate | Quality | Confidence | Decision |
| --- | --- | --- | --- |
| TRUE | ANY | ANY | DUPLICATE |
| FALSE | FAIL | ANY | REVIEW |
| FALSE | PASS | < 0.75 | REVIEW |
| FALSE | PASS | 0.75 - 0.8999 | REVIEW |
| FALSE | PASS | >= 0.90 | PUBLISH |

### Table 13
| # | Action | Component | Output |
| --- | --- | --- | --- |
| 1 | Source connector fetches job | Connector | Return normalized source payload + source metadata |
| 2 | Persist immutable raw job | Spring Boot | INSERT jobs_raw; calculate payload_hash |
| 3 | Publish JOB_RECEIVED | Outbox | Create event in same DB transaction |
| 4 | Start Flowable process | Workflow service | Process instance references jobRawId |
| 5 | Validate source/job | Validation Agent | Structured validation result |
| 6 | Check duplicates | Duplicate Agent + search tools | Duplicate candidates + score |
| 7 | Extract job metadata | Metadata/Location/Salary agents | Normalized metadata |
| 8 | Extract and resolve skills | Skills + Taxonomy agents | Controlled skill IDs + evidence |
| 9 | Classify job | Classification Agent | Industry/function/seniority taxonomy |
| 10 | Quality review | Quality Agent | Quality result + confidence |
| 11 | DMN gate | Flowable | PUBLISH / REVIEW / DUPLICATE |
| 12 | Human correction when needed | Flowable UI | Reviewer changes only relevant fields |
| 13 | Persist canonical job | Spring Boot | jobs + metadata + skills + source mapping |
| 14 | Create embedding | Embedding service/agent tool | Vector stored in job_embeddings |
| 15 | Publish searchable job | Search service | Status -> PUBLISHED |
| 16 | Generate candidate matches | Matching job/async worker | Candidate-specific scores |
| 17 | Send eligible notifications | Notification service | Policy checked delivery |

### Table 14
| Output | Source of truth | Agent role |
| --- | --- | --- |
| Job count by country | SQL/analytics | Explain |
| Skill demand trend | SQL/time-series job counts | Explain and compare |
| Median salary | Validated salary dataset | Explain with caveats |
| Forecast | Forecasting service | Summarize confidence interval |
| Career recommendation | Profile + analytics + matching | Reason across trusted outputs |

### Table 15
| Permission | Job Seeker | Recruiter | Employer | Admin |
| --- | --- | --- | --- | --- |
| JOB_SEARCH | ALLOW | ALLOW | ALLOW | ALLOW |
| CANDIDATE_SEARCH | DENY | ALLOW | ALLOW | ALLOW |
| JOB_CREATE_DRAFT | DENY | ALLOW | ALLOW | ALLOW |
| JOB_PUBLISH | DENY | POLICY | ALLOW | ALLOW |
| CANDIDATE_CONTACT | DENY | ALLOW | POLICY | ALLOW |
| TAXONOMY_UPDATE | DENY | DENY | DENY | ALLOW |
| BILLING_UPDATE | DENY | DENY | ALLOW_ADMIN_ONLY | ALLOW |
| SYSTEM_CONFIG | DENY | DENY | DENY | ALLOW |

### Table 16
| Action | Required controls |
| --- | --- |
| Publish job | Role permission + validation + Flowable publication state |
| Contact candidate | Role + tenant + candidate contact permission + audit |
| Change application status | Role + tenant + valid state transition + audit |
| Billing change | Employer billing permission + explicit confirmation + audit |
| Delete user/data | Admin permission + explicit confirmation + retention policy + audit |
| Taxonomy change | Admin + versioned taxonomy release + downstream re-index plan |

### Table 17
| Failure | Retry? | Max | Fallback |
| --- | --- | --- | --- |
| OpenAI network timeout | Yes | 3 | Flowable retry / incident |
| Rate limit | Yes | bounded backoff | Delayed retry |
| Invalid structured output | Yes | 2 | Schema repair attempt, then review |
| MCP 5xx | Yes | 3 | Fallback/error task |
| MCP 401/403 | No | 0 | Security error + alert |
| DB transient error | Yes | framework policy | Flowable retry |
| Unknown taxonomy | No automatic creation | 0 | Human taxonomy review |
| Low confidence | No retry | 0 | Human review |
| Provider delivery failure | Yes | policy based | notification retry/dead-letter |

### Table 18
| Metric | Why it matters |
| --- | --- |
| jobs.ingested.total | Source throughput |
| jobs.enrichment.success_rate | Pipeline health |
| jobs.review.rate | Agent confidence quality |
| agent.run.latency | Performance |
| agent.tool.error_rate | Tool health |
| agent.tokens / estimated_cost | AI spend |
| match.coverage | Candidate recommendation coverage |
| notification.delivery_rate | Engagement pipeline health |
| workflow.incidents | Flowable operational health |

### Table 19
| Method | Path | Purpose |
| --- | --- | --- |
| GET | /api/v1/jobs | Search jobs |
| GET | /api/v1/jobs/{jobId} | Job detail |
| POST | /api/v1/jobs/{jobId}/save | Save job |
| DELETE | /api/v1/jobs/{jobId}/save | Unsave |
| POST | /api/v1/jobs/{jobId}/apply | Create/track application |
| GET | /api/v1/users/me/matches | Recommended jobs |
| GET | /api/v1/users/me/profile | Get profile |
| PUT | /api/v1/users/me/profile | Update profile |
| POST | /api/v1/resumes | Upload resume |
| GET | /api/v1/resumes/{id} | Resume status/detail |
| POST | /api/v1/ai/career-assistant/messages | Career assistant |
| GET | /api/v1/notifications | Notifications |

### Table 20
| Method | Path | Purpose |
| --- | --- | --- |
| POST | /internal/v1/ingestion/jobs | Ingest one normalized raw job |
| POST | /internal/v1/workflows/job-enrichment | Start workflow |
| POST | /internal/v1/agent-runs/job-enrichment | Execute agent orchestration |
| POST | /internal/v1/agent-runs/resume | Resume extraction |
| GET | /internal/v1/workflows/{id} | Workflow status |
| POST | /internal/v1/reviews/{id}/decision | Human review decision |

### Table 21
| Area | Routes | Access |
| --- | --- | --- |
| Public | /, /jobs, /companies, /industries, /career-insights, /resources | Anonymous |
| Candidate | /app/dashboard, /app/jobs, /app/saved, /app/applications, /app/assistant, /app/learning, /app/market, /app/profile | Authenticated candidate roles |
| Recruiter | /recruiter/dashboard, /recruiter/jobs, /recruiter/candidates, /recruiter/interviews, /recruiter/reports | Recruiter |
| Employer | /employer/overview, /employer/jobs, /employer/candidates, /employer/analytics, /employer/team, /employer/billing | Employer |
| Admin | /admin, /admin/ingestion, /admin/quality, /admin/duplicates, /admin/ai-review, /admin/taxonomy, /admin/users, /admin/audit | Admin |

### Table 22
| Layer | Technology | Minimum tests |
| --- | --- | --- |
| Unit - Java | JUnit 5 | Domain rules, ranking, permissions, mappers |
| Unit - Python | Pytest | Agent wrappers, guardrails, schema validation |
| Repository | Testcontainers | PostgreSQL/pgvector queries |
| Integration | Spring Boot Test | API -> service -> DB, security, tenant rules |
| Workflow | Flowable test harness | BPMN paths and DMN decisions |
| Agent evaluation | Golden datasets | Extraction, taxonomy, duplicate, matching behavior |
| MCP | Contract tests | Tool schema, auth, tenant boundary, error mapping |
| UI | Playwright/Vitest | Route access, forms, search, responsive critical flows |
| E2E | Playwright + containers | Ingestion -> publish -> search -> candidate match |

### Table 23
| Phase | Name | Scope | Exit criterion |
| --- | --- | --- | --- |
| 0 | Foundation | Monorepo, Docker, PostgreSQL, Flyway, Spring Boot, Next.js, CI, AGENTS.md | Build passes; local login/search shell runs |
| 1 | Identity/RBAC | OIDC/JWT, roles, permissions, tenant model, audit | Access matrix tests pass |
| 2 | Ingestion | Sources, jobs_raw, source mappings, scheduler, Outbox | One source ingests raw jobs idempotently |
| 3 | Canonical Jobs | jobs, metadata, skills, companies, expiry | Canonical job read API works |
| 4 | Flowable | BPMN, DMN, review tasks, retries | Process runs end-to-end in test |
| 5 | Agent Runtime | OpenAI Agents SDK, orchestrator, validation, metadata, skills, taxonomy, quality | Structured enrichment result produced |
| 6 | MCP | Job, taxonomy, workflow, search MCP servers | Agent tools work through authenticated MCP |
| 7 | Agentic Job Pipeline | End-to-end enrichment, publish/review, embeddings | Golden path passes |
| 8 | Search | Filters, pgvector, ranking, natural language query plan | Search quality tests pass |
| 9 | Candidate Intelligence | Resume, profile, matching, skill gap, learning | Candidate gets useful matches |
| 10 | Career Assistant | Sessions, handoffs, tools, streaming, guardrails | Career flows pass |
| 11 | Recruiter/Employer | Candidate search, copilot, requisitions, job drafting | Tenant/security tests pass |
| 12 | Notifications/Market | Push/email/WhatsApp integration, market analytics | Delivery and data lineage pass |
| 13 | Scale | Kafka/Redpanda, OpenSearch, workers, Kubernetes | Load tests justify each scale component |

### Table 24
| Gate | Pass condition |
| --- | --- |
| Code quality | Build, unit tests and static checks pass |
| Security | RBAC and tenant tests pass; secrets scanning clean |
| Workflow | BPMN/DMN tests cover happy, review, duplicate and failure paths |
| AI evaluation | Golden dataset thresholds documented and met |
| Observability | Traces, metrics, structured logs and alerts available |
| Reliability | Retries/idempotency verified under replay |
| Data | Migrations and rollback plan tested |
| Operations | Runbook exists for ingestion, agent failures, MCP failures and Flowable incidents |
| Frontend | Critical persona routes and responsive flows tested |

### Table 25
| Risk / trade-off | Decision | Mitigation |
| --- | --- | --- |
| LLM nondeterminism | Use models only where reasoning adds value | Structured outputs, temperature/model policy, evaluations, confidence and human review |
| Too many agents | Keep domain-oriented agents to a manageable set | Start with ~10 core agents and grow based on business need |
| Agent cost | Avoid LLM calls for deterministic filtering/ranking | SQL/pgvector first, agents for explanation/ambiguity |
| MCP attack surface | Treat MCP as privileged internal infrastructure | Authentication, least privilege, input/output guardrails, audit |
| Workflow/agent confusion | Keep ownership explicit | Flowable = state/gates; agents = reasoning; services = actions |
| Data leakage | Agent context may carry sensitive data | Minimize context, tool authorization, redaction and logging policy |
| Scale complexity | Distributed systems add operational overhead | Start modular-monolith + agent service + Postgres; evolve with metrics |