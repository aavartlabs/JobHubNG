"""Weekly restore drill: prove the MinIO backups can actually be restored.

For each database it finds the newest daily backup (failing if it is older than
max_age_days, i.e. backups quietly stopped), downloads it, checks the SHA-256 recorded at
upload, decompresses it, runs SQLite's full integrity_check and makes sure the tables that
must never be empty aren't. Exits non-zero if anything fails, so the systemd unit shows it.

    python -m jobhub_poc.ops.restore_drill        # on pi09, from jobshub-restore-drill.timer

Uses ~/.jobshub-minio.env and ~/bin/mc like scripts/backup_to_minio.sh; the credentials
reach mc only through MC_HOST_jb.
"""
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

DAILY_PREFIX = "backups/daily/"


@dataclass(frozen=True)
class Target:
    host: str
    name: str
    nonempty_tables: tuple[str, ...] = ()


@dataclass
class Result:
    target: Target
    ok: bool = False
    date: str | None = None
    counts: dict = field(default_factory=dict)
    problem: str | None = None


def targets(env=os.environ):
    """The backups to check, by the host label they're uploaded under. When the databases
    move (e.g. to the Hostinger server, backed up by scripts/pull_backup.sh as "hostinger"),
    set JOBSHUB_DRILL_APP_HOST / JOBSHUB_DRILL_WAREHOUSE_HOST in the drill's environment."""
    app = env.get("JOBSHUB_DRILL_APP_HOST", "pi09")
    warehouse = env.get("JOBSHUB_DRILL_WAREHOUSE_HOST", "pi05")
    return (
        Target(app, "jobhub.db", ("jobs",)),
        Target(app, "auth.db", ("user", "account")),
        Target(warehouse, "warehouse.db", ("jobs", "ingest_runs")),
    )


TARGETS = targets()


def _check_one(store, target, today, max_age_days, workdir):
    result = Result(target)
    key = info = None
    for day in sorted(store.list_dates(DAILY_PREFIX), reverse=True):
        candidate = f"{DAILY_PREFIX}{day}/{target.host}/{target.name}.gz"
        info = store.stat(candidate)
        if info is not None:
            key, result.date = candidate, day
            break
    if key is None:
        result.problem = "no backup found"
        return result

    age = (today - date.fromisoformat(result.date)).days
    if age > max_age_days:
        result.problem = f"newest backup is {age} days old (limit {max_age_days})"
        return result

    gz_path = workdir / f"{target.host}-{target.name}.gz"
    db_path = workdir / f"{target.host}-{target.name}"
    try:
        store.download(key, gz_path)
        actual = hashlib.sha256(gz_path.read_bytes()).hexdigest()
        if info.get("sha256") and actual != info["sha256"]:
            result.problem = f"sha256 mismatch (stored {info['sha256'][:12]}…, downloaded {actual[:12]}…)"
            return result
        with gzip.open(gz_path) as src, open(db_path, "wb") as dst:
            shutil.copyfileobj(src, dst)
        conn = sqlite3.connect(db_path)
        try:
            check = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if check != "ok":
                result.problem = f"integrity_check: {check}"
                return result
            for table in target.nonempty_tables:
                result.counts[table] = conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
                if result.counts[table] == 0:
                    result.problem = f"{table} is empty"
                    return result
        finally:
            conn.close()
        result.ok = True
    except (OSError, sqlite3.DatabaseError, EOFError, gzip.BadGzipFile) as exc:
        result.problem = f"restore failed: {exc}"
    finally:
        gz_path.unlink(missing_ok=True)
        db_path.unlink(missing_ok=True)
    return result


def drill(store, targets, today, max_age_days, workdir):
    return [_check_one(store, t, today, max_age_days, Path(workdir)) for t in targets]


class McStore:
    """The drill's view of the bucket, through the mc CLI."""

    def __init__(self, mc, bucket, env):
        self.mc, self.bucket, self.env = mc, bucket, env

    def _run(self, *args):
        return subprocess.run([self.mc, *args], env=self.env, capture_output=True, text=True)

    def list_dates(self, prefix):
        out = self._run("ls", "--json", f"jb/{self.bucket}/{prefix}")
        dates = []
        for line in out.stdout.splitlines():
            entry = json.loads(line)
            if entry.get("type") == "folder":
                dates.append(entry["key"].rstrip("/"))
        return dates

    def stat(self, key):
        out = self._run("stat", "--json", f"jb/{self.bucket}/{key}")
        if out.returncode != 0:
            return None
        data = json.loads(out.stdout)
        meta = {k.lower(): v for k, v in (data.get("metadata") or {}).items()}
        return {"size": data.get("size"), "sha256": meta.get("x-amz-meta-sha256")}

    def download(self, key, dest):
        out = self._run("cp", "-q", f"jb/{self.bucket}/{key}", str(dest))
        if out.returncode != 0:
            raise OSError(out.stderr.strip() or "mc cp failed")


def _load_env(path):
    values = {}
    for line in Path(path).read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip()
    return values


def main():
    cfg = _load_env(os.environ.get("JOBSHUB_MINIO_ENV", Path.home() / ".jobshub-minio.env"))
    scheme, hostport = cfg["MINIO_ENDPOINT"].split("://", 1)
    env = {**os.environ, "MC_HOST_jb": f"{scheme}://{cfg['MINIO_ACCESS_KEY']}:{cfg['MINIO_SECRET_KEY']}@{hostport}"}
    store = McStore(os.environ.get("MC", str(Path.home() / "bin" / "mc")), cfg["MINIO_BUCKET"], env)
    with tempfile.TemporaryDirectory() as workdir:
        results = drill(store, targets(), today=date.today(), max_age_days=2, workdir=workdir)
    for r in results:
        status = "PASS" if r.ok else "FAIL"
        detail = ", ".join(f"{t}={n}" for t, n in r.counts.items()) if r.ok else r.problem
        print(f"{status} {r.target.host}/{r.target.name} [{r.date or '-'}] {detail}")
    failed = [r for r in results if not r.ok]
    print(f"restore drill: {len(results) - len(failed)}/{len(results)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
