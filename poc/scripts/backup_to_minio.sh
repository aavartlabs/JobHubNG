#!/usr/bin/env bash
# Nightly SQLite backups to MinIO on pi06 (bucket jobshub-data).
#
#   backup_to_minio.sh <host-label> <db-path> [<db-path> ...]
#   e.g. backup_to_minio.sh pi09 data/jobhub.db auth-service/data/auth.db
#
# For each database: SQLite online backup (a consistent copy of a live DB), quick_check,
# gzip, upload to backups/daily/<YYYY-MM-DD>/<label>/<name>.gz with its SHA-256 as object
# metadata, then re-read the object's size to verify the upload. On Sundays the object is
# also copied to backups/weekly/, on the 1st to backups/monthly/. The bucket's lifecycle
# rules expire daily/weekly/monthly after 14/84/365 days; this script never deletes.
#
# Credentials: ~/.jobshub-minio.env (MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY,
# MINIO_BUCKET; 0600), passed to mc only through the MC_HOST_jb environment variable --
# never on a command line. Overrides for tests: JOBSHUB_MINIO_ENV, MC, BACKUP_DATE.
set -euo pipefail

ENV_FILE=${JOBSHUB_MINIO_ENV:-$HOME/.jobshub-minio.env}
if [ -r "$ENV_FILE" ]; then set -a; . "$ENV_FILE"; set +a; fi
: "${MINIO_ENDPOINT:?MINIO_ENDPOINT not set (see $ENV_FILE)}"
: "${MINIO_ACCESS_KEY:?}" "${MINIO_SECRET_KEY:?}" "${MINIO_BUCKET:?}"
MC=${MC:-$HOME/bin/mc}

if [ $# -lt 2 ]; then
    echo "usage: $0 <host-label> <db-path> [<db-path> ...]" >&2
    exit 2
fi
LABEL=$1; shift
for db in "$@"; do
    [ -f "$db" ] || { echo "backup: $db not found -- nothing uploaded" >&2; exit 1; }
done

scheme=${MINIO_ENDPOINT%%://*}; hostport=${MINIO_ENDPOINT#*://}
export MC_HOST_jb="${scheme}://${MINIO_ACCESS_KEY}:${MINIO_SECRET_KEY}@${hostport}"
DATE=${BACKUP_DATE:-$(date +%F)}  # the host's local date (pi09/pi05 run in IST)
DOW=$(date -u -d "$DATE" +%u)
DOM=$(date -u -d "$DATE" +%d)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

for db in "$@"; do
    name=$(basename "$db")
    copy="$WORK/$name"
    python3 - "$db" "$copy" <<'PY'
import sqlite3, sys
src, dst = sqlite3.connect(sys.argv[1]), sqlite3.connect(sys.argv[2])
src.backup(dst)
result = dst.execute("PRAGMA quick_check").fetchone()[0]
dst.close(); src.close()
if result != "ok":
    sys.exit(f"quick_check failed on the backup copy: {result}")
PY
    gzip -6 -c "$copy" > "$copy.gz"
    sha=$(sha256sum "$copy.gz" | cut -d' ' -f1)
    size=$(stat -c %s "$copy.gz")
    key="$MINIO_BUCKET/backups/daily/$DATE/$LABEL/$name.gz"

    "$MC" cp --attr "sha256=$sha" "$copy.gz" "jb/$key" >/dev/null
    remote=$("$MC" stat --json "jb/$key" | python3 -c 'import json,sys; print(json.load(sys.stdin)["size"])')
    if [ "$remote" != "$size" ]; then
        echo "backup: size mismatch for $key (local $size, remote $remote)" >&2
        exit 1
    fi
    [ "$DOW" = 7 ] && "$MC" cp "jb/$key" "jb/$MINIO_BUCKET/backups/weekly/$DATE/$LABEL/$name.gz" >/dev/null
    [ "$DOM" = 01 ] && "$MC" cp "jb/$key" "jb/$MINIO_BUCKET/backups/monthly/$DATE/$LABEL/$name.gz" >/dev/null
    echo "backup: $LABEL/$name -> $key ($size bytes, sha256 $sha)"
done
