# JobHubNG — Sanjay’s Task List

**Role (per WhatsApp Delivery Plan):** Delivery Lead / Architect / Builder  
**Owns:** Delivery · Architecture · Code · Review  
**Does not own (Madhu):** Product prioritization · Portal UX sign-off · Client narrative · Requirements final say  

**Governing success criterion:** Madhu runs `docker compose up` and demos **Login → Ingest → Enrich → Review → Search → Match** in ~2 weeks.

Companion: `tasks_all.md` (full board including Madhu + backlog).

---

## Now — decisions only you can unblock

These are ahead of the day clock. Until they are answered, Day 1–2 work will thrash.

| # | Decision | Why it matters | Your lean (challenge me) |
| --- | --- | --- | --- |
| S0.1 | **Baseline:** adopt `artifacts/_unzipped/jobhub-agentic` as starting tree, or rebuild? | Zip already has LLD Phase 0+1 (auth/RBAC/outbox/Next shell/agent stub). Rebuilding burns Day 1–2. | **Adopt zip**, strip `__pycache__`, treat as baseline |
| S0.2 | **Stack authority:** LLD+zip (Java Spring + Python OpenAI Agents SDK + Next.js) vs E2E deck (Spring AI + ReactJS + Kong/Keycloak P2)? | Builders will fork if unclear. | **LLD+zip wins** for code; E2E deck is product vision only |
| S0.3 | **Schema:** incremental Flyway from zip V1/V2, or load full `JobHub_Complete_PostgreSQL_Schema_v1.0.sql`? | Full schema is ~1200 lines and broader than 2-week slice. | **Incremental Flyway**; pull tables as features need them |
| S0.4 | **Human review UI:** Flowable Task App vs custom `/admin/ai-review` in portal? | Day 8–10 critical path. | **Custom thin admin page** calling review API (Madhu-friendly demo) |
| S0.5 | **Demo hosting:** Madhu’s laptop Docker only, or you host a shared env? | Changes ops burden and “done” definition. | Start **local compose**; shared host only if Madhu can’t run Docker |
| S0.6 | **OpenAI:** which key/org, monthly cap, which model for enrichment vs embeddings? | Cost risk called out in plan. | Pin cheap model for enrichment; separate embedding model; hard daily cap |
| S0.7 | **IP / delivery boundary:** what is Aavart client deliverable vs Incorpify-generic? | Your operating rule: don’t ship Incorpify crown jewels as client-billed new work casually. | Clarify before first push to any client-visible repo |
| S0.8 | **Remote git:** GitHub under which org (Aavart vs personal vs Incorpify)? Visibility? | Needed before CI secrets and Madhu access. | Decide before Day 3 |
| S0.9 | **First ingest source:** fixture JSON upload, single ATS CSV, or EverJobs-shaped mock? | “160 sources” in Relay v7 is a trap. | **Fixture/mock connector** + `POST /internal/v1/ingestion/jobs` |
| S0.10 | **Clock start date:** when is Day 1? | Plan is 14 calendar days aggressive. | Name the date so Madhu Day 1–2 inputs have a deadline |

---

## Week 1

### Day 1–2 — Scaffold + DB

- [ ] **S1.** Confirm S0.1–S0.3 in writing (README or `ARCHITECTURE.md` one-pager).
- [ ] **S2.** Import chosen baseline into repo root (not left only under `artifacts/_unzipped`).
- [ ] **S3.** Clean junk from baseline (`__pycache__`, local `.pyc`, accidental secrets).
- [ ] **S4.** Make `docker compose up` bring Postgres(+pgvector) healthy with pinned image.
- [ ] **S5.** Verify Flyway V1/V2 apply; document how to reset DB.
- [ ] **S6.** Seed demo tenants + 6 personas (`*@jobhub.local` / `password` or rotate).
- [ ] **S7.** API `/actuator/health` green from compose or host run.
- [ ] **S8.** CI workflow builds platform-api (and web install) on push.
- [ ] **S9.** `.env.example` complete; real `.env` gitignored; OpenAI key path documented.
- [ ] **S10.** Push to remote (after S0.8); protect `main` if client-visible.
- [ ] **S11.** Block on Madhu: prioritized screens list + seed JDs + draft demo script (chase if late).

**Day 1–2 exit:** clean clone → compose → migrations → health. No enrichment yet.

### Day 3–4 — Auth + RBAC + portal shell

- [ ] **S12.** Demo login + `/me` returns role/permissions for all personas.
- [ ] **S13.** Method-level RBAC: admin dataflow 200 / seeker 403 (automated test).
- [ ] **S14.** Login writes `audit_events` + `outbox_events`; publisher → `PUBLISHED`.
- [ ] **S15.** Tenant_id on employer-owned paths (P1 app-level filter only — no RLS yet).
- [ ] **S16.** Next.js login + persona portal shell talks to real API (not mock-only).
- [ ] **S17.** Implement **only** Madhu-prioritized routes; stub the rest with “not in MVP” states.
- [ ] **S18.** Cross-tenant / cross-role negative tests from LLD §26.3 (minimum set).
- [ ] **S19.** Review Madhu UX feedback; fix blockers only.

**Day 3–4 exit:** Madhu can log in as Admin and Seeker and see role-appropriate shell.

### Day 5–7 — Ingest + Flowable + first agent

- [ ] **S20.** Tables: `job_sources`, `jobs_raw` (+ hash uniqueness), minimal company if needed.
- [ ] **S21.** `POST /internal/v1/ingestion/jobs` — admin-only; immutable raw; idempotent.
- [ ] **S22.** Same transaction: insert raw + `JOB_RECEIVED` outbox.
- [ ] **S23.** Flowable process definition `JobEnrichmentProcess(jobRawId)` starts from outbox/handler.
- [ ] **S24.** Python agent runtime: orchestrator + **one** specialist with structured Pydantic/JSON schema.
- [ ] **S25.** Persist `ai_processing_runs` (agent, model, confidence, output_json, trace_id).
- [ ] **S26.** Agent talks via tool/MCP or internal HTTP — **never** direct Postgres credentials.
- [ ] **S27.** Correlation IDs across HTTP → workflow → agent span (log at least).
- [ ] **S28.** Internal demo Friday: one job in → workflow instance → one AI result in DB/UI.
- [ ] **S29.** Resist adding Duplicate/Skills/Taxonomy yet unless Day 5–6 finished early.

**Week 1 exit:** vertical stub of the pipeline exists; not full DMN/publish yet.

---

## Week 2

### Day 8–10 — Agents + DMN + human review

- [ ] **S30.** Minimum specialist set for demo: Duplicate, Metadata, Skills, Taxonomy resolve, Quality.
- [ ] **S31.** DMN table aligned to LLD Table 12 (PUBLISH / REVIEW / DUPLICATE).
- [ ] **S32.** On REVIEW: create human task + API `POST /internal/v1/reviews/{id}/decision`.
- [ ] **S33.** Ship human-review UI per S0.4 (thin admin page preferred).
- [ ] **S34.** On PUBLISH: write canonical `jobs` + metadata + skills + source mapping.
- [ ] **S35.** Embedding → `job_embeddings` (dimension pinned to model).
- [ ] **S36.** Replay same payload: no second canonical job; no duplicate notify side effects.
- [ ] **S37.** Tests: happy publish path + forced low-confidence review path.
- [ ] **S38.** Cost check: token usage on seed batch; adjust model/temperature if needed.

### Day 11–12 — Search + candidate match

- [ ] **S39.** `GET /api/v1/jobs` with filters + vector similarity.
- [ ] **S40.** Search UI on prioritized screen.
- [ ] **S41.** Minimal resume/profile path (seed resume OK if upload slips).
- [ ] **S42.** `job_matches` with score components + explanation + formula version.
- [ ] **S43.** Candidate matches UI (“why” + skill gap); copy must not claim hiring decision.
- [ ] **S44.** E2E scripted path automated or checklist-runnable by Madhu alone.

### Day 13 — Polish + demo

- [ ] **S45.** Demo data reset script (`make demo-reset` or equivalent).
- [ ] **S46.** Runbook: ports, accounts, failure modes, “what to do if OpenAI is down”.
- [ ] **S47.** Known limitations doc (honest OUT list).
- [ ] **S48.** Joint demo with Madhu driving; you on call for breakage.
- [ ] **S49.** Triage feedback into P0 (demo-blocking) vs later.

### Day 14 — Buffer

- [ ] **S50.** Fix P0 only.
- [ ] **S51.** Freeze scope; tag `demo-2026-XX-XX` release.
- [ ] **S52.** Write handoff note: what Madhu can show client vs what is vapor.

---

## Ongoing (every day)

- [ ] **S53.** Enforce WhatsApp OUT list — say no to Kafka/OpenSearch/K8s/full agents/recruiter copilots/deep polish.
- [ ] **S54.** Codex/agent PRs: you remain architecture authority; compare to LLD + this list.
- [ ] **S55.** No production deploys / client pushes without your explicit send approval (operating rule).
- [ ] **S56.** Keep secrets out of git; rotate if anything leaked into chat/logs.
- [ ] **S57.** End of each day: one-line status Madhu can read (blocked / done / tomorrow).

---

## Explicitly not your job (push back if dumped on you)

| Item | Owner |
| --- | --- |
| Which portal screens matter for client story | Madhu |
| Demo script narrative and client messaging | Madhu |
| Final product requirements / acceptance taste | Madhu |
| Seed job content realism / domain copy | Madhu |
| Deep visual polish / Relay parity | Out of 2-week scope |
| Full EverJobs 160-source integration | Out |
| Production multi-tenant / Keycloak / Kong | Out (Product P2) |

If Madhu Day 1–2 inputs (screens, demo script, seed jobs) are missing by end of your Day 2, **escalate the same day** — do not invent product priorities silently.

---

## Suggested first commits (once S0.* answered)

1. Import baseline + `.gitignore` + remove caches  
2. `ARCHITECTURE.md` stating chosen stack + phase glossary  
3. Compose + Flyway smoke green  
4. Auth/RBAC tests green  
5. Ingestion + Flowable hello  
6. First agent structured result  
7. DMN + review  
8. Search + match  
9. Demo tag  

---

## Definition of Done (your bar)

You are done with the 2-week delivery when **Madhu**, without you driving the keyboard, can:

1. Start the stack from the runbook  
2. Log in  
3. Ingest a job  
4. Show enrichment / review  
5. Search the published job  
6. Show a candidate match with explanation  

If that path works and OUT-of-scope items stayed out, you met the Delivery Lead contract — even if the full LLD remains mostly unimplemented.
