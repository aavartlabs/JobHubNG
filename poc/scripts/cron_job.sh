#!/usr/bin/env bash
# Run one scheduled JobsHub job from cron (hosts without systemd user linger, e.g. the
# Hostinger server): never two at once, low CPU/IO priority so the host's other sites come
# first, output appended to logs/<name>.log, and the admin told if it fails
# (jobhub_poc.ops.alert_admin, Telegram else WhatsApp).
#
#   cron_job.sh pipeline env SCRAPER_HOST=local scripts/run_pipeline_warehouse.sh
set -uo pipefail

NAME=${1:?usage: cron_job.sh <name> <command...>}
shift
APP_DIR=${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
cd "${APP_DIR}"
mkdir -p logs
LOG="logs/${NAME}.log"

exec 9>"logs/.${NAME}.lock"
if ! flock -n 9; then
    echo "$(date -Is) ${NAME}: previous run still going, skipped" >> "${LOG}"
    exit 0
fi

echo "== $(date -Is) ${NAME} start ==" >> "${LOG}"
nice -n 10 ionice -c 3 "$@" >> "${LOG}" 2>&1
STATUS=$?
echo "== $(date -Is) ${NAME} exit ${STATUS} ==" >> "${LOG}"
if [ "${STATUS}" -ne 0 ]; then
    .venv/bin/python -m jobhub_poc.ops.alert_admin "${NAME}" "${LOG}" >> "${LOG}" 2>&1
fi
exit "${STATUS}"
