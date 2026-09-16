.PHONY: test test-scraper venv seed web dump load purge alerts pipeline

venv:
	python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt

test:
	.venv/bin/pytest -v

test-scraper:
	cd scraper && .venv/bin/pytest -v

seed:
	.venv/bin/python scripts/seed_demo_user.py

seed-demo-data:
	.venv/bin/python scripts/seed_demo_data.py

web:
	.venv/bin/python -m jobhub_poc.webapp.app

dump:
	cd scraper && .venv/bin/python dump_jobs.py

load:
	.venv/bin/python -m jobhub_poc.loader.load_dump $(DUMP)

purge:
	.venv/bin/python -m jobhub_poc.loader.purge

alerts:
	.venv/bin/python -m jobhub_poc.alerts.run_alerts

pipeline:
	bash scripts/run_pipeline.sh
