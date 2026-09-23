#!/usr/bin/env bash
# Warehouse-era pipeline (Stage 2). Runs ON pi09, like run_pipeline.sh -- which stays in
# place, unchanged, as the rollback until the cutover is confirmed.
#
# 1. ingest on pi05   -> full EverJobs sweep upserted into pi05's warehouse.db (no dump)
# 2. export on pi05   -> gzip delta of rows updated since pi09's watermark that pass the
#                        serving filter in config/pipeline.ini
# 3. pull + load      -> scp the delta, upsert into jobhub.db, advance the watermark
# 4. purge + alerts   -> locally, as before
set -euo pipefail

PI05_DIR=${PI05_DIR:-/home/rudra/jobhub-poc}
APP_DIR=${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
REMOTE_DELTA=/tmp/jobhub_delta.jsonl.gz
TERMS_FILE=/tmp/jobhub_alert_terms.json
LOCAL_DELTA=$(mktemp /tmp/jobhub_delta.XXXXXX.jsonl.gz)
NEW_IDS=/tmp/jobhub_poc_new_ids.json
trap 'rm -f "${LOCAL_DELTA}"' EXIT
cd "${APP_DIR}"

echo "== 1/4: warehouse ingest on pi05 =="
ssh pi05 "cd ${PI05_DIR}/scraper && .venv/bin/python ingest.py"

echo "== 2/4: export delta on pi05 =="
SINCE=$(.venv/bin/python -m jobhub_poc.loader.load_delta --print-watermark)
# Active alerts' titles/keywords widen what pi05 exports (T14). When that set changes
# (an alert was added or edited), re-scan the whole warehouse so matching jobs it already
# holds come through too; load_delta keeps those from being announced as new.
TERMS_FP=$(.venv/bin/python -m jobhub_poc.alerts.alert_terms --out "${TERMS_FILE}")
PREV_TERMS_FP=$(.venv/bin/python -m jobhub_poc.loader.load_delta --print-terms-fingerprint)
if [ "${TERMS_FP}" != "${PREV_TERMS_FP}" ]; then
    echo "alert terms changed (${PREV_TERMS_FP:-none} -> ${TERMS_FP}): full re-scan"
    SINCE=""
fi
scp -q "${TERMS_FILE}" "pi05:${TERMS_FILE}"
EXPORT_JSON=$(ssh pi05 "cd ${PI05_DIR}/scraper && .venv/bin/python export.py --out ${REMOTE_DELTA} --extra-terms-file ${TERMS_FILE} ${SINCE:+--since '${SINCE}'}")
echo "${EXPORT_JSON}"
WATERMARK=$(printf '%s' "${EXPORT_JSON}" | .venv/bin/python -c 'import json,sys; print(json.loads(sys.stdin.read().strip().splitlines()[-1])["watermark"] or "")')

echo "== 3/4: pull + load delta =="
scp -q "pi05:${REMOTE_DELTA}" "${LOCAL_DELTA}"
.venv/bin/python -m jobhub_poc.loader.load_delta "${LOCAL_DELTA}" ${WATERMARK:+--watermark "${WATERMARK}"} \
    --terms-fingerprint "${TERMS_FP}" --new-ids-out "${NEW_IDS}"

echo "== 4/4: purge + alerts (local) =="
.venv/bin/python -m jobhub_poc.loader.purge
if [ "${SUPPRESS_ALERTS:-0}" = "1" ]; then
    # The first sync after cutover inserts thousands of jobs that aren't really new;
    # announcing them would spam every subscriber. Run it once with SUPPRESS_ALERTS=1.
    echo "alerts suppressed for this run (SUPPRESS_ALERTS=1)"
else
    .venv/bin/python -m jobhub_poc.alerts.run_alerts --new-ids "${NEW_IDS}"
fi

echo "== pipeline complete =="
