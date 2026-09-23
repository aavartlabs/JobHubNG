"""scripts/backup_to_minio.sh against a stub `mc` that keeps 'uploads' in a temp dir."""
import gzip
import hashlib
import json
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "backup_to_minio.sh"

STUB_MC = r'''#!/usr/bin/env python3
import json, os, shutil, sys
from pathlib import Path
store = Path(os.environ["STUB_STORE"])
log = Path(os.environ["STUB_LOG"])
args = sys.argv[1:]
log.open("a").write(json.dumps(args) + "\n")
def local(target):  # jb/bucket/key -> store/bucket/key
    return store / target.split("/", 1)[1]
if args[0] == "cp":
    attrs = [a for a in args if a.startswith("--attr")]
    src, dst = [a for a in args[1:] if not a.startswith("--attr") and a not in attrs][-2:]
    meta = {}
    if "--attr" in args:
        for kv in args[args.index("--attr") + 1].split(";"):
            k, v = kv.split("=", 1); meta[k] = v
    out = local(dst); out.parent.mkdir(parents=True, exist_ok=True)
    if os.environ.get("STUB_CORRUPT") and not src.startswith("jb/"):
        out.write_bytes(b"truncated")
    else:
        shutil.copyfile(local(src) if src.startswith("jb/") else src, out)
    if meta: out.with_suffix(out.suffix + ".meta").write_text(json.dumps(meta))
elif args[0] == "stat":
    p = local(args[-1])
    meta_file = p.with_suffix(p.suffix + ".meta")
    meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}
    print(json.dumps({"size": p.stat().st_size, "metadata": {f"X-Amz-Meta-{k.capitalize()}": v for k, v in meta.items()}}))
else:
    sys.exit(f"unexpected mc call {args}")
'''


def _db(path, rows=3):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.executemany("INSERT INTO t (v) VALUES (?)", [(f"row{i}",) for i in range(rows)])
    conn.commit()
    conn.close()
    return path


def _run(tmp_path, *dbs, date="2026-09-24", extra_env=None):
    stub = tmp_path / "mc"
    stub.write_text(STUB_MC)
    stub.chmod(0o755)
    store, log = tmp_path / "store", tmp_path / "mc.log"
    env = {**os.environ, "MC": str(stub), "STUB_STORE": str(store), "STUB_LOG": str(log),
           "BACKUP_DATE": date, "MINIO_ENDPOINT": "http://minio.test:9000", "MINIO_ACCESS_KEY": "k",
           "MINIO_SECRET_KEY": "s", "MINIO_BUCKET": "jobshub-data", "JOBSHUB_MINIO_ENV": "/dev/null",
           **(extra_env or {})}
    proc = subprocess.run(["bash", str(SCRIPT), "pi09", *map(str, dbs)], env=env, capture_output=True, text=True)
    calls = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
    return proc, store, calls


def test_daily_backup_is_a_gzipped_consistent_copy_with_checksum(tmp_path):
    db = _db(tmp_path / "jobhub.db", rows=5)
    proc, store, _ = _run(tmp_path, db)
    assert proc.returncode == 0, proc.stderr
    obj = store / "jobshub-data/backups/daily/2026-09-24/pi09/jobhub.db.gz"
    restored = tmp_path / "restored.db"
    restored.write_bytes(gzip.decompress(obj.read_bytes()))
    assert sqlite3.connect(restored).execute("SELECT count(*) FROM t").fetchone()[0] == 5
    meta = json.loads(obj.with_suffix(".gz.meta").read_text())
    assert meta["sha256"] == hashlib.sha256(obj.read_bytes()).hexdigest()


def test_sunday_also_copies_to_weekly_and_the_first_to_monthly(tmp_path):
    db = _db(tmp_path / "auth.db")
    _, store, _ = _run(tmp_path, db, date="2026-09-27")  # a Sunday
    assert (store / "jobshub-data/backups/weekly/2026-09-27/pi09/auth.db.gz").exists()
    assert not (store / "jobshub-data/backups/monthly").exists()
    _, store, _ = _run(tmp_path, db, date="2026-10-01")  # a Thursday, 1st of month
    assert (store / "jobshub-data/backups/monthly/2026-10-01/pi09/auth.db.gz").exists()


def test_several_databases_in_one_run(tmp_path):
    a, b = _db(tmp_path / "jobhub.db"), _db(tmp_path / "auth.db")
    proc, store, _ = _run(tmp_path, a, b)
    assert proc.returncode == 0
    day = store / "jobshub-data/backups/daily/2026-09-24/pi09"
    assert sorted(p.name for p in day.glob("*.gz")) == ["auth.db.gz", "jobhub.db.gz"]


def test_a_size_mismatch_after_upload_fails_the_run(tmp_path):
    proc, _, _ = _run(tmp_path, _db(tmp_path / "jobhub.db"), extra_env={"STUB_CORRUPT": "1"})
    assert proc.returncode != 0
    assert "size mismatch" in proc.stderr


def test_missing_database_fails_loudly_without_uploading(tmp_path):
    proc, store, calls = _run(tmp_path, tmp_path / "nope.db")
    assert proc.returncode != 0
    assert calls == []


def test_credentials_never_reach_the_command_line(tmp_path):
    _, _, calls = _run(tmp_path, _db(tmp_path / "jobhub.db"))
    assert calls and not any("s" == a or "k:s" in a for call in calls for a in call)
