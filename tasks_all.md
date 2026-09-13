# JobHubNG — Master Task List

**Created:** 2026-09-11  
**Sources reviewed:**
- WhatsApp Delivery Plan screenshots (2026-09-09) — *governing near-term plan*
- `JobHub_Agentic_MultiAgent_Low_Level_Design_v1.0.md` (+ DOCX)
- `JobHub_Complete_PostgreSQL_Schema_v1.0.sql`
- `jobhub-agentic-phase0-phase1.zip` (scaffold claiming LLD Phase 0+1 done)
- `JobHub-Agentic-E2E-Platform v0.1.pdf` (product/architecture deck)
- `JobHub - Agentic Intellinence Platform.pdf` (vision one-pager)
- Portal / Relay HTML prototypes
- Unzipped scaffold docs (`README`, `AGENTS.md`, `codex-task-phase0-1.md`)

**Owners:**
| Owner | Role (per delivery plan) |
| --- | --- |
| **Sanjay** | Delivery Lead / Architect / Builder — Delivery, Architecture, Code, Review |
| **Madhu** | Product / Portal UX / Client / Requirements |
| **Shared** | Needs both; blocked until aligned |
| **Codex/Agent** | Implementation accelerator under Sanjay review (not architecture authority) |

---

## 0. Critical glossary — three different “Phase” systems

Do not mix these. The 2-week WhatsApp plan says **“Phase 0+1”** but its day plan covers what the LLD calls **Phases 0–9**.

| Label | Meaning | Scope |
| --- | --- | --- |
| **Delivery “Phase 0+1”** (WhatsApp) | 2-week MVP slice | Foundation → first E2E: login → ingest → enrich → review → search → match |
| **LLD Phases 0–13** (Table 23) | Engineering roadmap | 0 Foundation … 9 Candidate Intelligence … 13 Scale |
| **Product Phase 1 / Phase 2** (E2E deck) | MVP vs Scale-Up | P1 = local/containers, JWT, pgvector, Flowable in-process; P2 = Kafka, OpenSearch, Keycloak, K8s, WhatsApp, etc. |

**Zip scaffold status:** Implements *LLD* Phase 0 + Phase 1 only (monorepo, Postgres/Flyway, demo JWT, RBAC, audit/outbox, Next shell, agent runtime stub, CI skeleton). It does **not** implement the WhatsApp 2-week E2E slice.

**Explicitly OUT of the 2-week delivery (WhatsApp):**
- Full agent catalog
- Kafka / OpenSearch / Kubernetes
- Production multi-tenant hardening
- Recruiter / Employer copilots
- Deep UI polish

**Success criterion (WhatsApp):** Madhu can run `docker compose up` and demo **Login → Ingest → Enrich → Review → Search → Match**.

---

## A. Kickoff / alignment (before coding day clock starts)

| ID | Task | Owner | Status | Notes |
| --- | --- | --- | --- | --- |
| A1 | Confirm governing plan = WhatsApp 2-week Delivery Plan (not full LLD, not E2E deck P2) | Shared | Open | See grill questions |
| A2 | Resolve phase-numbering language for client/Madhu communications | Shared | Open | Avoid “Phase 0+1” ambiguity |
| A3 | Decide: adopt zip scaffold as baseline vs rebuild from LLD | Sanjay | Open | Zip exists and claims 0+1 done |
| A4 | Resolve stack conflicts (Python OpenAI Agents SDK vs Spring AI; Next.js vs ReactJS deck; Kong/Keycloak timing) | Sanjay | Open | LLD + zip = Python Agents SDK + Next.js; E2E deck = Spring AI + ReactJS |
| A5 | Confirm frontend source of truth among portal HTML, Relay v5, Relay v7, Next shell | Shared | Open | Madhu owns UX priority |
| A6 | Confirm single job source for first ingest (not “160 EverJobs sources”) | Shared | Open | LLD: one source idempotent first |
| A7 | Agree demo script + seed data requirements | Madhu (draft) / Sanjay (feasibility) | Open | Madhu Day 1–2 |
| A8 | Confirm commercial/IP boundary (Incorpify vs Aavart; what ships to client) | Sanjay | Open | Per operating rules |
| A9 | Provision secrets: OpenAI key, DB passwords; decide cost budget/cap | Sanjay | Open | Never commit secrets |
| A10 | Choose human-review UX: Flowable Task App vs custom admin page in portal | Shared | Open | Affects Week 2 Day 8–10 |
| A11 | Decide hosting for demo: local-only vs shared Docker host for Madhu | Shared | Open | Success criterion is `docker compose up` |
| A12 | Write SOW / acceptance checklist Madhu will sign off against | Shared | Open | Map to WhatsApp success path |
| A13 | Create remote git repo + branch strategy (main protected, feature branches) | Sanjay | Open | Local `git init` already done |
| A14 | Pin versions: JDK/Spring Boot/Flowable, Python/openai-agents, Node, Postgres+pgvector image | Sanjay | Open | LLD warns Flowable↔Spring Boot coupling |

---

## B. Week 1 — Sanjay build + Madhu product inputs

### Day 1–2 — Scaffold + DB

| ID | Task | Owner | Maps to |
| --- | --- | --- | --- |
| B1 | Land monorepo in JobHubNG (from zip or fresh per A3) | Sanjay | LLD §7, Phase 0 |
| B2 | Docker Compose: Postgres + pgvector (+ Redis if needed) | Sanjay | LLD §8.5, §29.1 |
| B3 | Flyway foundation migrations (tenants/users/RBAC/audit/outbox) | Sanjay | Schema V1 / zip V1 |
| B4 | Decide schema strategy: incremental Flyway from zip vs import full `JobHub_Complete_PostgreSQL_Schema_v1.0.sql` | Sanjay | Conflict to resolve |
| B5 | Seed taxonomy / demo tenants / demo users | Sanjay | zip DemoDataSeeder |
| B6 | README + `.env.example` + `AGENTS.md` usable by Madhu and Codex | Sanjay | zip already has stubs |
| B7 | CI skeleton green (build + unit smoke) | Sanjay | zip `.github/workflows/ci.yml` |
| B8 | **Madhu:** Prioritize portal screens for 2-week demo | Madhu | WhatsApp Day 1–2 |
| B9 | **Madhu:** Draft demo script (persona, clicks, talking points) | Madhu | WhatsApp Day 1–2 |
| B10 | **Madhu:** Provide / approve seed job examples (realistic JDs) | Madhu | WhatsApp Day 1–2 |
| B11 | Smoke: `docker compose up`, API health, DB migrations apply | Sanjay | Codex Task Pack Task 1 |

### Day 3–4 — Auth + RBAC + portal shell

| ID | Task | Owner | Maps to |
| --- | --- | --- | --- |
| B12 | Demo JWT auth (`/api/v1/auth/demo-login`, `/me`) for all personas | Sanjay | LLD Phase 1; zip Auth* |
| B13 | RBAC matrix enforcement + tests (admin vs seeker on admin routes) | Sanjay | LLD Table 15; Codex Tasks 2–3 |
| B14 | Tenant model (shared schema + `tenant_id`; app-level filter) — Product P1 level only | Sanjay | E2E deck P1; LLD §21.3 |
| B15 | Audit + outbox on login path; publisher marks PUBLISHED | Sanjay | Codex Task 4 |
| B16 | Next.js shell: login + persona-aware portal wired to API | Sanjay | LLD §25; zip `apps/web` |
| B17 | Wire navigation to Madhu-prioritized screens only (stubs OK elsewhere) | Sanjay | Depends B8 |
| B18 | **Madhu:** Review/approve login + portal shell UX | Madhu | WhatsApp Day 3–7 |
| B19 | Security tests: cross-role denial, anonymous denial | Sanjay | LLD §26.3 |

### Day 5–7 — Ingest + Flowable + first agent

| ID | Task | Owner | Maps to |
| --- | --- | --- | --- |
| B20 | `jobs_raw` + ingestion API (`POST /internal/v1/ingestion/jobs`) | Sanjay | LLD Phase 2; Table 20 |
| B21 | Immutable raw payload + `payload_hash` idempotency | Sanjay | LLD §10.3, P6 |
| B22 | Outbox `JOB_RECEIVED` in same transaction as raw insert | Sanjay | LLD Table 13 #2–3 |
| B23 | Flowable `JobEnrichmentProcess` BPMN skeleton started from event | Sanjay | LLD Phase 4; Table 13 #4 |
| B24 | Agent runtime: Job Enrichment Orchestrator + **one** specialist (recommend: Validation or Metadata) | Sanjay | LLD Phase 5; WhatsApp Day 5–7 |
| B25 | Structured output schema + persist `ai_processing_runs` | Sanjay | LLD §10.5 |
| B26 | MCP or service-tool boundary for that one agent (no direct DB from agent) | Sanjay | LLD P2; Phase 6 minimal |
| B27 | Trace correlation: request / workflow / agent run IDs | Sanjay | LLD §23 |
| B28 | **Madhu:** Product decisions on enrichment fields shown in UI | Madhu | WhatsApp Day 3–7 |
| B29 | Week-1 demo internally: login → ingest one job → workflow started → one agent result visible | Sanjay | Internal gate |

---

## C. Week 2 — Complete E2E slice

### Day 8–10 — Remaining core agents + DMN + human review

| ID | Task | Owner | Maps to |
| --- | --- | --- | --- |
| C1 | Add specialist agents needed for demo: Duplicate, Metadata, Skills, Taxonomy, Quality (minimum set) | Sanjay | LLD Table 9 subset |
| C2 | DMN confidence gate (PUBLISH / REVIEW / DUPLICATE) per Table 12 | Sanjay | LLD §15.3 |
| C3 | Human review task creation + decision API | Sanjay | LLD Table 20; Phase 4 |
| C4 | Human review UI (per A10 decision) | Sanjay (+ Madhu UX) | WhatsApp Day 8–10 |
| C5 | Canonical job persist on PUBLISH path (`jobs`, metadata, skills, source mapping) | Sanjay | LLD Phase 3 + 7 |
| C6 | Embedding write to `job_embeddings` (pgvector) | Sanjay | LLD §10.6 |
| C7 | Idempotent re-run: same raw input does not duplicate canonical job | Sanjay | Acceptance §30.1 |
| C8 | **Madhu:** Prepare client narrative / slide story for demo | Madhu | WhatsApp Day 8–12 |
| C9 | Golden path automated test: high-confidence publish + low-confidence review | Sanjay | LLD §30.1 |

### Day 11–12 — Search + candidate match

| ID | Task | Owner | Maps to |
| --- | --- | --- | --- |
| C10 | Job search API: filters + pgvector semantic retrieval | Sanjay | LLD Phase 8 |
| C11 | Search UI (Madhu-prioritized screen) | Sanjay / Madhu UX | Portal |
| C12 | Resume upload or seed resume → profile/skills extraction (minimal) | Sanjay | LLD Phase 9 |
| C13 | Matching worker: store `job_matches` with score + explanation | Sanjay | LLD Phase 9; §30.2 |
| C14 | Candidate “why matched / skill gap” UI | Sanjay / Madhu UX | Acceptance §30.2 |
| C15 | **Madhu:** Validate match explanations are client-presentable | Madhu | Day 8–12 |
| C16 | Guardrail: never present match as final hiring decision | Sanjay | LLD §30.2 |

### Day 13 — Polish + demo

| ID | Task | Owner | Maps to |
| --- | --- | --- | --- |
| C17 | End-to-end polish: empty/error states, request IDs, demo data reset script | Sanjay | WhatsApp Day 13 |
| C18 | Runbook: how Madhu starts stack and runs demo | Sanjay | zip `docs/runbook.md` |
| C19 | **Joint demo:** Madhu drives; Sanjay on standby | Shared | Success criterion |
| C20 | Capture feedback / defect list | Madhu | WhatsApp Day 13–14 |

### Day 14 — Buffer

| ID | Task | Owner | Maps to |
| --- | --- | --- | --- |
| C21 | Fix demo-blocking defects only | Sanjay | WhatsApp Day 14 |
| C22 | Explicitly defer non-demo scope (document in README “Out of scope”) | Sanjay | Anti-overscoping |
| C23 | **Madhu:** Final feedback + go/no-go for client showing | Madhu | Day 13–14 |

---

## D. Delivery risks to manage (from plan)

| ID | Risk | Mitigation task | Owner |
| --- | --- | --- | --- |
| D1 | AI extraction quality poor for demo | Curate seed jobs; lower demo bar; human-review path as feature not failure | Sanjay + Madhu |
| D2 | Over-scoping into full LLD / P2 deck | Enforce WhatsApp OUT list daily | Sanjay |
| D3 | Flowable learning curve | Keep BPMN minimal; one process; tests early | Sanjay |
| D4 | OpenAI cost | Cap model; cache/idempotency; budget alarm | Sanjay |
| D5 | Stack doc conflicts confuse builders | Single `ARCHITECTURE.md` stating chosen stack | Sanjay |

---

## E. Post–2-week backlog (LLD / Product P2 — not in current delivery)

Do **not** start these in the 2-week window unless A1 is revised.

| ID | Task | LLD / Product phase |
| --- | --- | --- |
| E1 | Career Assistant (sessions, handoffs, streaming) | LLD Phase 10 |
| E2 | Recruiter / Employer copilots, requisitions, job drafting | LLD Phase 11 — WhatsApp OUT |
| E3 | Notifications (email/SMS/WhatsApp) + market intelligence | LLD Phase 12 |
| E4 | Kafka/Redpanda, OpenSearch, workers, Kubernetes | LLD Phase 13 / Product P2 — WhatsApp OUT |
| E5 | Keycloak OIDC, Kong gateway, RLS / schema-per-tenant | Product P2 |
| E6 | Full agent catalog (~22 agents in Table 9) | WhatsApp OUT |
| E7 | Golden datasets at LLD scale (500 jobs, 100 resumes, etc.) | LLD §26.2 — scale later |
| E8 | Production HA Postgres, secret manager, OTel full stack | LLD §29.2 |
| E9 | Mobile / GraphQL BFF | Product P2 channels |
| E10 | EverJobs / 160-source connector farm | Prototypes only for now |

---

## F. Definition of Done — 2-week delivery

- [ ] `docker compose up --build` brings up web + API + agent runtime + Postgres
- [ ] Madhu logs in as demo personas
- [ ] Admin/ops can ingest a raw job
- [ ] Enrichment workflow runs; AI result stored and visible
- [ ] Low-confidence path creates human review; decision resumes workflow
- [ ] High-confidence / approved job becomes searchable
- [ ] Candidate sees at least one match with explanation
- [ ] Docs: README, runbook, demo script, known limitations
- [ ] No Kafka / OpenSearch / K8s / recruiter-employer copilots shipped as “done”

---

## G. Artifact map (what each file is for)

| Artifact | Role |
| --- | --- |
| WhatsApp delivery screenshots | **Near-term contract** (2 weeks, owners, success path) |
| LLD v1.0 | Implementation contract / architecture authority |
| Complete PostgreSQL schema SQL | Target schema reference (do not dump wholesale into Week 1) |
| phase0-phase1.zip | Candidate code baseline for LLD 0+1 |
| E2E Platform PDF | Product vision + P1/P2 capability ladder (not 2-week backlog) |
| Agentic Intelligence one-pager | Marketing / positioning |
| `jobhub_portal.html` + Relay HTML | UX prototypes for Madhu prioritization |
| Codex task pack in zip | Verification checklist for foundation only |
