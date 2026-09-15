# Local Runbook

1. `docker compose up -d postgres`
2. `cd apps/platform-api && ./mvnw spring-boot:run`
3. `cd apps/web && npm install && npm run dev`
4. Open `http://localhost:3000`
5. Sign in using a demo account.
6. Admin can inspect the audit/outbox counts in the portal.
7. Optional: start the agent runtime on port 8090; it is intentionally a health-only scaffold in Phase 0/1.

## Cleanup

`docker compose down`

To remove DB data too: `docker compose down -v`.
