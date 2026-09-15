# JobHubNG

Agentic Job Intelligence Platform.

## Quick Start

```bash
cp .env.example .env
# Add your OPENAI_API_KEY to .env
docker compose up --build
```

- API: http://localhost:8080
- Web: http://localhost:3000

## Demo Accounts

| Persona | Email | Password |
|---------|-------|----------|
| Admin | admin@jobhub.local | password |
| Seeker | seeker@jobhub.local | password |
| Fresher | fresher@jobhub.local | password |
| Professional | professional@jobhub.local | password |
| Recruiter | recruiter@jobhub.local | password |
| Employer | employer@jobhub.local | password |

## Architecture

```
Next.js 15 → Spring Boot 3.3 → PostgreSQL 16 + pgvector
                    ↑
            Spring AI (agents as @Tool methods)
```

**Stack:**
- **Backend:** Java 21 + Spring Boot 3.3 + Spring Data JPA + Spring AI
- **Frontend:** Next.js 15
- **Database:** PostgreSQL 16 + pgvector
- **Auth:** Spring Security + JWT
- **Workflow:** State machine (no Flowable)

## Development

```bash
# Backend only
cd apps/platform-api && ./mvnw spring-boot:run

# Frontend only
cd apps/web && npm install && npm run dev

# Smoke test
bash scripts/smoke-test.sh
```
