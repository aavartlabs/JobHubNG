#!/usr/bin/env bash
# Nightly backups of every JobsHub database on this one host (the Hostinger server): the
# serving DB, the accounts DB and the scraper's warehouse, all under one label, through
# scripts/backup_to_minio.sh to the S3 store in $JOBSHUB_MINIO_ENV (R2 there:
# MINIO_ENDPOINT=https://<account>.r2.cloudflarestorage.com). The Pis keep nightly_backup.sh.
#
#   JOBSHUB_MINIO_ENV=~/.jobshub-r2.env scripts/nightly_backup_local.sh
set -euo pipefail

APP_DIR=${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
LABEL=${LABEL:-hostinger}

echo "== $(date -Is) backup ${LABEL} =="
bash "${APP_DIR}/scripts/backup_to_minio.sh" "${LABEL}" \
    "${APP_DIR}/data/jobhub.db" "${APP_DIR}/auth-service/data/auth.db" "${APP_DIR}/scraper/data/warehouse.db"
