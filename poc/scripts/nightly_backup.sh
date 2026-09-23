#!/usr/bin/env bash
# Nightly backups of every JobsHub database to MinIO (pi06). Runs on pi09 from
# jobshub-backup.timer; pi05's warehouse is backed up over SSH, the same way the pipeline
# drives pi05, so pi05 needs no timer of its own (its user has no systemd linger).
# Each host reads its own ~/.jobshub-minio.env; see scripts/backup_to_minio.sh.
set -euo pipefail

APP_DIR=${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
PI05_DIR=${PI05_DIR:-jobhub-poc}  # relative: ssh commands start in the remote home
status=0

echo "== $(date -Is) backup pi09 =="
bash "$APP_DIR/scripts/backup_to_minio.sh" pi09 \
    "$APP_DIR/data/jobhub.db" "$APP_DIR/auth-service/data/auth.db" || status=1

echo "== $(date -Is) backup pi05 (over ssh) =="
ssh pi05 "bash ${PI05_DIR}/scripts/backup_to_minio.sh pi05 ${PI05_DIR}/scraper/data/warehouse.db" || status=1

# One host failing must not skip the other, but the unit must still show as failed.
exit $status
