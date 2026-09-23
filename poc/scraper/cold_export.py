"""CLI (pi05, monthly): move old job history from warehouse.db to MinIO.

Rows in jobs_archive archived more than [archive] cold_after_days ago, and job_versions
whose span ended that long ago, are written as gzip JSON-lines -- one row per line, with
version JSON decompressed so the files read without zlib -- and uploaded to
jobshub-data/archive/history/<date>/{jobs_archive,job_versions}.jsonl.gz (never expires).
Only after each upload is verified (size re-read from MinIO) are those rows deleted from
the warehouse; any failure deletes nothing, and the next month simply tries again.

    .venv/bin/python cold_export.py         # run over ssh from pi09's jobshub-cold-export.timer
"""
import gzip
import hashlib
import json
import os
import subprocess
import sys
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobhub_poc.pipeline_config import load_pipeline_config  # noqa: E402
from ingest import DEFAULT_DB_PATH  # noqa: E402
from warehouse import open_warehouse  # noqa: E402


def _write_jsonl_gz(path, rows):
    with gzip.open(path, "wt") as f:
        for row in rows:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")


def _upload_verified(uploader, path, key):
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    stored = uploader.upload(path, key, sha)
    if stored != path.stat().st_size:
        raise RuntimeError(f"upload of {key} not verified (local {path.stat().st_size}, stored {stored})")


def export_cold(conn, cold_after_days, uploader, workdir, now=None):
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=cold_after_days)).isoformat()
    prefix = f"archive/history/{now.date().isoformat()}"
    workdir = Path(workdir)

    archived = [dict(r) for r in conn.execute(
        "SELECT * FROM jobs_archive WHERE archived_at < ? ORDER BY archive_id", (cutoff,))]
    versions = []
    for r in conn.execute("SELECT * FROM job_versions WHERE valid_to < ? ORDER BY id", (cutoff,)):
        row = dict(r)
        row["raw_json"] = json.loads(zlib.decompress(row.pop("raw_json_z")))
        versions.append(row)

    if archived:
        path = workdir / "jobs_archive.jsonl.gz"
        _write_jsonl_gz(path, archived)
        _upload_verified(uploader, path, f"{prefix}/jobs_archive.jsonl.gz")
    if versions:
        path = workdir / "job_versions.jsonl.gz"
        _write_jsonl_gz(path, versions)
        _upload_verified(uploader, path, f"{prefix}/job_versions.jsonl.gz")

    # Every upload above succeeded and was verified; only now remove the rows.
    with conn:
        conn.executemany("DELETE FROM jobs_archive WHERE archive_id = ?", [(r["archive_id"],) for r in archived])
        conn.executemany("DELETE FROM job_versions WHERE id = ?", [(r["id"],) for r in versions])
    return {"archived_jobs": len(archived), "versions": len(versions)}


class McUploader:
    """Uploads through ~/bin/mc with credentials from ~/.jobshub-minio.env (MC_HOST_jb)."""

    def __init__(self):
        cfg = {}
        env_file = Path(os.environ.get("JOBSHUB_MINIO_ENV", Path.home() / ".jobshub-minio.env"))
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
        scheme, hostport = cfg["MINIO_ENDPOINT"].split("://", 1)
        self.bucket = cfg["MINIO_BUCKET"]
        self.mc = os.environ.get("MC", str(Path.home() / "bin" / "mc"))
        self.env = {**os.environ,
                    "MC_HOST_jb": f"{scheme}://{cfg['MINIO_ACCESS_KEY']}:{cfg['MINIO_SECRET_KEY']}@{hostport}"}

    def upload(self, path, key, sha256):
        target = f"jb/{self.bucket}/{key}"
        put = subprocess.run([self.mc, "cp", "-q", "--attr", f"sha256={sha256}", str(path), target],
                             env=self.env, capture_output=True, text=True)
        if put.returncode != 0:
            raise RuntimeError(f"upload of {key} failed: {put.stderr.strip()}")
        stat = subprocess.run([self.mc, "stat", "--json", target], env=self.env, capture_output=True, text=True)
        if stat.returncode != 0:
            raise RuntimeError(f"could not stat {key} after upload")
        return json.loads(stat.stdout)["size"]


def main():
    import tempfile

    cfg = load_pipeline_config()
    conn = open_warehouse(os.environ.get("WAREHOUSE_DB_PATH", DEFAULT_DB_PATH))
    try:
        with tempfile.TemporaryDirectory() as workdir:
            stats = export_cold(conn, cfg.archive.cold_after_days, McUploader(), workdir)
        if stats["archived_jobs"] or stats["versions"]:
            conn.execute("VACUUM")  # hand the freed pages back to the disk
    finally:
        conn.close()
    print(json.dumps({"cold_export": stats, "cold_after_days": cfg.archive.cold_after_days}))


if __name__ == "__main__":
    main()
