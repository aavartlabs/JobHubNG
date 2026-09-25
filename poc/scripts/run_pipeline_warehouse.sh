#!/usr/bin/env bash
# Warehouse-era pipeline (Stage 2). Runs ON pi09, like run_pipeline.sh -- which stays in
# place, unchanged, as the rollback until the cutover is confirmed.
#
# 1. ingest on pi05   -> full EverJobs sweep upserted into pi05's warehouse.db (no dump)
#    + enrich on pi05 -> fill what EverJobs leaves out (SmartRecruiters descriptions and
#                        links, scraper/enrich.py); best effort, never stops the run
# 2. export on pi05   -> gzip delta of rows updated since pi09's watermark that pass the
#                        serving filter in config/pipeline.ini
# 3. pull + load      -> scp the delta, upsert into jobhub.db, advance the watermark
# 4. purge + alerts   -> locally, as before
#
# SCRAPER_HOST=local runs the scraper steps on this machine (scraper/ next to the app, its
# own venv) with plain copies instead of ssh/scp -- both tiers on one host. The two
# databases and the delta/watermark hand-over are the same either way.
set -euo pipefail

SCRAPER_HOST=${SCRAPER_HOST:-pi05}
PI05_DIR=${PI05_DIR:-jobhub-poc}  # relative: ssh commands start in the remote home
APP_DIR=${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
REMOTE_DELTA=${REMOTE_DELTA:-/tmp/jobhub_delta.jsonl.gz}
TERMS_FILE=${TERMS_FILE:-/tmp/jobhub_alert_terms.json}
LOCAL_DELTA=$(mktemp /tmp/jobhub_delta.XXXXXX.jsonl.gz)
NEW_IDS=${NEW_IDS:-/tmp/jobhub_poc_new_ids.json}
trap 'rm -f "${LOCAL_DELTA}"' EXIT
cd "${APP_DIR}"

# Run a command in the scraper directory, wherever the scraper lives.
on_scraper() {
    if [ "${SCRAPER_HOST}" = "local" ]; then
        (cd "${APP_DIR}/scraper" && bash -c "$1")
    else
        ssh "${SCRAPER_HOST}" "cd ${PI05_DIR}/scraper && $1"
    fi
}
to_scraper() {  # <local file> <path on the scraper host>
    if [ "${SCRAPER_HOST}" = "local" ]; then [ "$1" = "$2" ] || cp "$1" "$2"; else scp -q "$1" "${SCRAPER_HOST}:$2"; fi
}
from_scraper() {  # <path on the scraper host> <local file>
    if [ "${SCRAPER_HOST}" = "local" ]; then cp "$1" "$2"; else scp -q "${SCRAPER_HOST}:$1" "$2"; fi
}

echo "== 1/4: warehouse ingest on ${SCRAPER_HOST} =="
on_scraper ".venv/bin/python ingest.py"
echo "== 1b/4: enrich on ${SCRAPER_HOST} =="
on_scraper ".venv/bin/python enrich.py" || echo "enrich failed (continuing without it)"

echo "== 2/4: export delta on ${SCRAPER_HOST} =="
SINCE=$(.venv/bin/python -m jobhub_poc.loader.load_delta --print-watermark)
# Active alerts' titles/keywords widen what pi05 exports (T14). When that set changes
# (an alert was added or edited), re-scan the whole warehouse so matching jobs it already
# holds come through too; load_delta keeps those from being announced as new.
TERMS_FP=$(.venv/bin/python -m jobhub_poc.alerts.alert_terms --out "${TERMS_FILE}")
PREV_TERMS_FP=$(.venv/bin/python -m jobhub_poc.loader.load_delta --print-terms-fingerprint)
if [ "${TERMS_FP}" != "${PREV_TERMS_FP}" ]; then
    echo "alert terms changed (${PREV_TERMS_FP:-none} -> ${TERMS_FP}): full re-scan"
    SINCE=""
elif [ "${FULL_SYNC:-0}" = "1" ]; then
    # On request: every matching warehouse row in full -- e.g. to send descriptions enriched
    # in earlier runs (before the watermark), which a normal delta never picks up again.
    echo "full re-scan requested (FULL_SYNC=1)"
    SINCE=""
fi
to_scraper "${TERMS_FILE}" "${TERMS_FILE}"
EXPORT_JSON=$(on_scraper ".venv/bin/python export.py --out ${REMOTE_DELTA} --extra-terms-file ${TERMS_FILE} ${SINCE:+--since '${SINCE}'}")
echo "${EXPORT_JSON}"
WATERMARK=$(printf '%s' "${EXPORT_JSON}" | .venv/bin/python -c 'import json,sys; print(json.loads(sys.stdin.read().strip().splitlines()[-1])["watermark"] or "")')

echo "== 3/4: pull + load delta =="
from_scraper "${REMOTE_DELTA}" "${LOCAL_DELTA}"
.venv/bin/python -m jobhub_poc.loader.load_delta "${LOCAL_DELTA}" ${WATERMARK:+--watermark "${WATERMARK}"} \
    --terms-fingerprint "${TERMS_FP}" --new-ids-out "${NEW_IDS}"

echo "== 4/4: purge + alerts (local) =="
.venv/bin/python -m jobhub_poc.loader.purge
# Every listed job gets read (job_reading.py: Muse drafts, Jev decides) in the background,
# so match badges and filters don't wait for someone to open it.
.venv/bin/python -m jobhub_poc.ai.queue_reads || echo "queueing job readings failed (continuing)"
if [ "${SUPPRESS_ALERTS:-0}" = "1" ]; then
    # The first sync after cutover inserts thousands of jobs that aren't really new;
    # announcing them would spam every subscriber. Run it once with SUPPRESS_ALERTS=1.
    echo "alerts suppressed for this run (SUPPRESS_ALERTS=1)"
else
    .venv/bin/python -m jobhub_poc.alerts.run_alerts --new-ids "${NEW_IDS}"
fi

echo "== pipeline complete =="
