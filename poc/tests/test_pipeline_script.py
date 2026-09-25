"""scripts/run_pipeline_warehouse.sh with SCRAPER_HOST=local: every step runs here, no ssh.
Both venvs are stand-ins that log what they were asked to run."""
import os
import shutil
import stat
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "run_pipeline_warehouse.sh"

FAKE_PYTHON = """#!/usr/bin/env bash
echo "$(basename "$PWD") $*" >> "$LOG"
case "$*" in
  *'["watermark"]'*) cat > /dev/null; echo w2 ;;
  *export.py*) out=$(echo "$*" | sed -E 's/.*--out ([^ ]+).*/\\1/'); echo delta > "$out"; echo '{"watermark": "w2"}' ;;
  *--print-watermark*) echo "2026-09-25T00:00:00+00:00" ;;
  *--print-terms-fingerprint*) echo "fp1" ;;
  *alert_terms*) echo "fp1" ;;
esac
"""


def _venv(root):
    python = root / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text(FAKE_PYTHON)
    python.chmod(python.stat().st_mode | stat.S_IEXEC)


def _run(tmp_path, **extra):
    app = tmp_path / "app"
    (app / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, app / "scripts" / SCRIPT.name)
    _venv(app)
    _venv(app / "scraper")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("ssh", "scp"):  # any use of them fails the run
        (bin_dir / tool).write_text("#!/bin/sh\necho \"$0 must not be used\" >&2\nexit 99\n")
        (bin_dir / tool).chmod(0o755)
    log = tmp_path / "calls.log"
    env = {**os.environ, "SCRAPER_HOST": "local", "LOG": str(log), "PATH": f"{bin_dir}:{os.environ['PATH']}",
           "REMOTE_DELTA": str(tmp_path / "delta.jsonl.gz"), "TERMS_FILE": str(tmp_path / "terms.json"),
           "NEW_IDS": str(tmp_path / "new_ids.json")}
    result = subprocess.run(["bash", str(app / "scripts" / SCRIPT.name)], env={**env, **extra}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result, log.read_text().splitlines()


def test_local_mode_runs_every_step_without_ssh(tmp_path):
    result, calls = _run(tmp_path)
    scraper = [c for c in calls if c.startswith("scraper ")]
    assert [c.split()[1] for c in scraper] == ["ingest.py", "enrich.py", "export.py"]
    assert "--since 2026-09-25T00:00:00+00:00" in scraper[2]
    assert any("load_delta /tmp/jobhub_delta." in c and "--watermark w2" in c for c in calls)
    assert f"--out {tmp_path}/delta.jsonl.gz" in scraper[2]
    assert any("jobhub_poc.loader.purge" in c for c in calls) and any("run_alerts" in c for c in calls)
    assert any("jobhub_poc.ai.queue_reads" in c for c in calls)
    assert "pipeline complete" in result.stdout


def test_full_sync_exports_everything_without_a_watermark(tmp_path):
    result, calls = _run(tmp_path, FULL_SYNC="1")
    export = next(c for c in calls if c.startswith("scraper export.py"))
    assert "--since" not in export and "full re-scan requested (FULL_SYNC=1)" in result.stdout
