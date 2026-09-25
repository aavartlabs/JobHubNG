#!/usr/bin/env bash
# Nightly backup of a remote JobsHub host (the Hostinger server) into MinIO on the LAN.
# The remote can't reach MinIO (and shouldn't), so a LAN host pulls: on the remote, a
# consistent SQLite online backup of each database into a temp dir; scp the copies here;
# then scripts/backup_to_minio.sh uploads them as usual under the label "$LABEL".
# Runs on pi09 in place of nightly_backup.sh once the site has moved.
#
#   REMOTE=testprepup REMOTE_DIR=aavartlabs/jobshub scripts/pull_backup.sh
set -euo pipefail

APP_DIR=${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
REMOTE=${REMOTE:-testprepup}
REMOTE_DIR=${REMOTE_DIR:-aavartlabs/jobshub}  # relative: ssh commands start in the remote home
LABEL=${LABEL:-hostinger}
DBS=(data/jobhub.db auth-service/data/auth.db scraper/data/warehouse.db)

LOCAL=$(mktemp -d)
REMOTE_TMP=$(ssh "${REMOTE}" mktemp -d)
cleanup() { rm -rf "${LOCAL}"; ssh "${REMOTE}" "rm -rf '${REMOTE_TMP}'" || true; }
trap cleanup EXIT

echo "== $(date -Is) snapshot on ${REMOTE} =="
# One python3 call for all three: sqlite3's backup API gives a consistent copy of a live DB.
ssh "${REMOTE}" "cd ${REMOTE_DIR} && python3 - ${REMOTE_TMP} ${DBS[*]}" <<'PY'
import os, sqlite3, sys
out, dbs = sys.argv[1], sys.argv[2:]
for db in dbs:
    src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    dst = sqlite3.connect(os.path.join(out, os.path.basename(db)))
    src.backup(dst)
    dst.close(); src.close()
    print(f"copied {db}")
PY

echo "== $(date -Is) pull + upload as ${LABEL} =="
for db in "${DBS[@]}"; do
    scp -q "${REMOTE}:${REMOTE_TMP}/$(basename "${db}")" "${LOCAL}/"
done
bash "${APP_DIR}/scripts/backup_to_minio.sh" "${LABEL}" "${LOCAL}"/*.db
