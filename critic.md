# JobHub Architecture Critique & Modernization Proposal

**Date:** 2026-09-15  
**Scope:** LLD v1.0 + zip scaffold + current implementation state  
**Verdict:** Solid domain design, but the tech stack is bleeding-edge in ways that will slow the team down. Recommend targeted swaps.

---

## 1. What's Good (Don't Change)

- **Domain boundaries are clean.** Spring Boot owns business logic, agents reason, PostgreSQL is system of record. This is correct.
- **Outbox pattern before Kafka.** Right call for MVP. Don't add Kafka until you need it.
- **Immutable `jobs_raw` + `payload_hash` idempotency.** Good event-sourcing foundation.
- **Hybrid matching formula (keyword + semantic + skill).** Correct — don't let the LLM be the database.
- **Agent guardrails in the LLD.** "Agents never directly access PostgreSQL" is the right rule.
- **Tenant isolation via `tenant_id` + app-level filters.** Appropriate for P1.

---

## 2. Critical Issues

### 2.1 Spring Boot 4.1.1 Is Too New

**Problem:** Spring Boot 4.1.1 (part of Spring Framework 7) is bleeding-edge. We hit three compatibility issues in one session:
- `flowable-spring-boot-starter` not in the BOM → needs explicit version
- `flyway-spring-boot-starter` not in the BOM → needs explicit version  
- Jackson 3 renamed `WRITE_DATES_AS_TIMESTAMPS` → config breakage
- `ObjectMapper` not auto-configured → needed a custom `@Configuration` class

**Recommendation:** Downgrade to **Spring Boot 3.3.x** (or 3.4.x). It's the current mature line with:
- Full Flowable 8 compatibility
- Flyway starter in the BOM
- Jackson 2.x (stable config)
- Spring AI 1.0 GA support
- Much larger community knowledge base

The scaffold was written for Spring Boot 4.1.1 because the LLD said so, but the LLD is a design doc, not a compatibility matrix. Spring Boot 3.x is the safer foundation.

### 2.2 JDBC Template Instead of JPA

**Problem:** The scaffold uses `JdbcTemplate` directly. For a domain this rich (20+ entities, complex relationships), raw JDBC means:
- Manual mapping everywhere
- No lazy loading, no dirty checking
- More boilerplate, more bugs

**Recommendation:** Use **Spring Data JPA** with Hibernate. Keep `JdbcTemplate` for the outbox publisher (where you need raw SQL control), but use JPA for everything else. The LLD even says `spring-boot-starter-data-jpa` in §8.4 but the scaffold doesn't include it.

### 2.3 Flowable Is Overkill for MVP

**Problem:** Flowable 8 BPMN/DMN adds:
- 45+ database tables (we saw them: `act_ru_*`, `act_hi_*`, etc.)
- Heavyweight process engine startup
- DMN engine compatibility issues (the `DmnEngineConfigurator` class missing)
- Steep learning curve

For the 2-week MVP, the workflow is: `receive → validate → enrich → gate → publish/review`. That's a state machine, not a BPMN process.

**Recommendation:** Replace Flowable with a **Spring State Machine** or even a simple `status` column + service methods. You can always add Flowable later when you need:
- Human task assignment with a UI
- Complex retry/compensation logic
- Visual process monitoring

For now, a `JobStatus` enum (`RECEIVED → VALIDATING → ENRICHING → PUBLISHING → PUBLISHED/REVIEW/REJECTED`) with service methods is simpler, faster, and testable.

### 2.4 MCP Servers Add Premature Complexity

**Problem:** The LLD defines 9 MCP servers (job, candidate, resume, search, taxonomy, workflow, analytics, learning, notification). Each is a separate process with its own port. For MVP, this means:
- 9 extra services to deploy and monitor
- Network hop for every agent tool call
- MCP protocol overhead for what could be a local method call

**Recommendation:** Skip MCP for MVP. Have the agent runtime call Spring Boot APIs directly via HTTP (or better, use Spring AI's `@Tool` method pattern). MCP makes sense when:
- You have multiple agent frameworks consuming the same tools
- You want to expose tools to third parties
- You need strict process isolation

None of these apply to a 2-week MVP with one Python agent runtime.

### 2.5 OpenAI Agents SDK = Vendor Lock-in

**Problem:** The agent runtime is built on `openai-agents==0.22.1`. If you want to switch models (Anthropic, Gemini, open-source), you rewrite the agent layer.

**Recommendation:** Use **Spring AI** instead. It's:
- Model-agnostic (OpenAI, Anthropic, Gemini, Ollama, etc.)
- Already integrated with Spring Boot
- Has `@Tool` annotation for exposing Java methods as agent tools
- Has observability built in
- The LLD already mentions it in §8.4

This also lets you write agents in Java (no Python runtime needed), simplifying deployment to one JVM.

---

## 3. Recommended Modern Stack

| Layer | Current | Recommended | Why |
|---|---|---|---|
| Backend | Spring Boot 4.1.1 | **Spring Boot 3.3.x** | Stable, compatible, well-documented |
| Persistence | JdbcTemplate | **Spring Data JPA** + Hibernate | Less boilerplate, better for rich domain |
| Workflow | Flowable BPMN/DMN | **Spring State Machine** or status enum | Lighter, no DB bloat, faster startup |
| Agent Runtime | Python + OpenAI Agents SDK | **Spring AI** (Java) | Model-agnostic, single runtime, no Python |
| Agent Tools | MCP servers (planned) | **Spring AI `@Tool` methods** | No extra services, direct method calls |
| Frontend | Next.js 16.3.4 | **Next.js 15** (LTS) | Stable, larger ecosystem |
| Auth | Manual JWT | **Spring Security OAuth2** + Keycloak (later) | Standard, testable |
| Database | PostgreSQL 17 + pgvector | **PostgreSQL 16** + pgvector | pg17 is very new; pg16 is battle-tested |
| Build | Maven | **Maven** (keep) | Fine for Java monorepo |
| CI | GitHub Actions | **GitHub Actions** (keep) | Fine |

---

## 4. Simplified Architecture (MVP)

```
┌─────────────────────────────────────────────────────┐
│  Next.js 15 Frontend (App Router)                   │
│  - Login / Portal / Search / Match UI               │
│  - API calls to platform-api                        │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP
┌──────────────────────▼──────────────────────────────┐
│  Spring Boot 3.3 (platform-api)                     │
│  ┌─────────────────────────────────────────────┐    │
│  │ Spring Security (JWT)                       │    │
│  │ Spring Data JPA + Hibernate                 │    │
│  │ Spring AI (agent tools as @Tool methods)    │    │
│  │ Flyway migrations                           │    │
│  │ Outbox pattern (JdbcTemplate)               │    │
│  └─────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────┐    │
│  │ Job State Machine                           │    │
│  │ RECEIVED → VALIDATING → ENRICHING →         │    │
│  │   PUBLISHING → PUBLISHED/REVIEW/REJECTED    │    │
│  └─────────────────────────────────────────────┘    │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  PostgreSQL 16 + pgvector                           │
│  - jobs_raw (immutable)                             │
│  - jobs (canonical)                                 │
│  - job_embeddings (vector search)                   │
│  - audit_events, outbox_events                      │
│  - users, roles, permissions                        │
└─────────────────────────────────────────────────────┘
```

**Key changes:**
- No Python agent runtime → agents run in JVM via Spring AI
- No Flowable → state machine in service layer
- No MCP → direct `@Tool` method calls
- One fewer language to maintain
- One fewer container in Docker Compose

---

## 5. What to Keep from the LLD

These parts of the LLD are excellent and should survive any stack change:

1. **Agent catalog design** (Table 9) — the agent responsibilities are well-defined
2. **Structured output contracts** — `JobEnrichmentResult`, `AgentResult` schemas
3. **Idempotency key pattern** — `JOB_ENRICHMENT:{jobRawId}:{payloadHash}`
4. **Matching formula** — the weighted blend is correct
5. **Guardrails** — "never present match as final hiring decision"
6. **Audit fields** — correlation_id, trace_id, actor, tenant
7. **Outbox pattern** — atomic event publication

---

## 6. Migration Path

If you agree with the recommendations:

1. **Now (Week 1):** Downgrade to Spring Boot 3.3, add Spring Data JPA, remove Flowable, add Spring AI
2. **Week 2:** Implement job state machine, agent tools as `@Tool` methods, wire frontend
3. **Post-MVP:** Add Keycloak for OAuth2, add Kafka if event volume demands it, add Flowable if human task UI becomes complex

---

## 7. Risks of the Current Path

- **Spring Boot 4.x compatibility** will continue to bite with every library upgrade
- **Flowable 8 + Spring Boot 4** is untested in production (we hit `DmnEngineConfigurator` missing)
- **Python + Java** means two build systems, two debuggers, two deployment stories
- **MCP for MVP** is distributed system overhead for a single-team project
- **Next.js 16** is very new; some libraries may not support it yet

---

*This critique is based on the LLD v1.0, CLAUDE.md, AGENTS.md, and hands-on experience getting the scaffold to build. The goal is to reduce risk and speed up delivery, not to redesign the domain model.*
