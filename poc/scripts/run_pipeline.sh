#!/usr/bin/env bash
# Orchestration entrypoint. Run ON the app host itself (pi09) -- pulls the
# scrape dump directly from pi05 over SSH/scp. No relay host involved; a
# third always-on host was never actually required, only pi05<->pi09 SSH
# trust, which now exists.
#
# 1. scrape on pi05          -> writes a timestamped JSON dump there
# 2. pull that dump          -> pi05 -> this host, direct scp
# 3. load + purge + alert    -> locally, against the SQLite DB
set -euo pipefail

PI05_SCRAPER_DIR=${PI05_SCRAPER_DIR:-jobhub-poc/scraper}  # relative to the remote home
# Defaults to the poc/ checkout this script lives under, so it works
# unmodified wherever the app host's role ends up (this host today, a
# different one later -- see tasks_all.md's "moving off Raspberry Pi
# hardware" note).
APP_DIR=${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}

echo "== 1/3: scraping on pi05 =="
ssh pi05 "cd ${PI05_SCRAPER_DIR} && .venv/bin/python dump_jobs.py"

LATEST_DUMP=$(ssh pi05 "ls -t ${PI05_SCRAPER_DIR}/dumps/*.json | head -1")
DUMP_NAME=$(basename "${LATEST_DUMP}")
echo "latest dump: ${DUMP_NAME}"

echo "== 2/3: pulling dump from pi05 =="
mkdir -p "${APP_DIR}/dumps"
scp -q "pi05:${LATEST_DUMP}" "${APP_DIR}/dumps/${DUMP_NAME}"

echo "== 3/3: load + purge + alerts (local) =="
cd "${APP_DIR}"
.venv/bin/python -m jobhub_poc.loader.load_dump "dumps/${DUMP_NAME}" --new-ids-out /tmp/jobhub_poc_new_ids.json
.venv/bin/python -m jobhub_poc.loader.purge
.venv/bin/python -m jobhub_poc.alerts.run_alerts --new-ids /tmp/jobhub_poc_new_ids.json

echo "== pipeline complete =="
