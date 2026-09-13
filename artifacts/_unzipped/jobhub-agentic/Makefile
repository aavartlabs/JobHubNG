up:
	docker compose up -d --build

run-api:
	cd apps/platform-api && ./mvnw spring-boot:run

run-web:
	cd apps/web && npm install && npm run dev

run-agent:
	cd apps/agent-runtime && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && uvicorn jobhub_agents.main:app --reload --port 8090

smoke:
	./scripts/smoke-test.sh

down:
	docker compose down
