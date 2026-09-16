#!/usr/bin/env bash
# Orchestration entrypoint. Run FROM harita (or any host with passwordless SSH
# aliases `pi05` and `pi09` already configured, per ~/.ssh/config).
#
# 1. scrape on pi05          -> writes a timestamped JSON dump
# 2. relay that dump         -> pi05 -> harita -> pi09 (no assumed pi05<->pi09 trust)
# 3. load + purge + alert    -> on pi09, against the SQLite DB
set -euo pipefail

# NOTE: bash tilde-expands defaults like ${VAR:-~/x} using the LOCAL host's
# $HOME at assignment time (this runs on harita), not the remote host's --
# so these must be literal absolute paths, not ~-prefixed.
PI05_SCRAPER_DIR=${PI05_SCRAPER_DIR:-/home/rudra/jobhub-poc/scraper}
PI09_APP_DIR=${PI09_APP_DIR:-/home/sanjayu/jobhub-poc}

echo "== 1/3: scraping on pi05 =="
ssh pi05 "cd ${PI05_SCRAPER_DIR} && .venv/bin/python dump_jobs.py"

LATEST_DUMP=$(ssh pi05 "ls -t ${PI05_SCRAPER_DIR}/dumps/*.json | head -1")
DUMP_NAME=$(basename "${LATEST_DUMP}")
echo "latest dump: ${DUMP_NAME}"

echo "== 2/3: relaying dump pi05 -> harita -> pi09 =="
STAGE=$(mktemp -d)
trap 'rm -rf "${STAGE}"' EXIT
scp -q "pi05:${LATEST_DUMP}" "${STAGE}/${DUMP_NAME}"
ssh pi09 "mkdir -p ${PI09_APP_DIR}/dumps"
scp -q "${STAGE}/${DUMP_NAME}" "pi09:${PI09_APP_DIR}/dumps/${DUMP_NAME}"

echo "== 3/3: load + purge + alerts on pi09 =="
ssh pi09 "cd ${PI09_APP_DIR} && .venv/bin/python -m jobhub_poc.loader.load_dump dumps/${DUMP_NAME} --new-ids-out /tmp/jobhub_poc_new_ids.json"
ssh pi09 "cd ${PI09_APP_DIR} && .venv/bin/python -m jobhub_poc.loader.purge"
ssh pi09 "cd ${PI09_APP_DIR} && .venv/bin/python -m jobhub_poc.alerts.run_alerts --new-ids /tmp/jobhub_poc_new_ids.json"

echo "== pipeline complete =="
