"""CLI (pi05): fetch one EverJobs sweep and upsert it, unfiltered, into warehouse.db.

The successor to dump_jobs.py. Nothing is filtered or capped here -- the serving filter is
applied later, at export (T5) -- and no dump file is written unless
[retention] keep_raw_dumps_days > 0 in config/pipeline.ini (then a gzip of the raw sweep,
for debugging). Prints the run's counts as one JSON line.

    .venv/bin/python ingest.py            # WAREHOUSE_DB_PATH defaults to ./data/warehouse.db
"""
import gzip
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobhub_poc.pipeline_config import load_pipeline_config  # noqa: E402
from warehouse import ingest, open_warehouse, purge_warehouse  # noqa: E402

DEFAULT_DB_PATH = "./data/warehouse.db"
RAW_DUMP_DIR = "./raw_dumps"


def _fetch_from_everjobs():
    import config
    from everjobs_client import EverJobsClient

    client = EverJobsClient(
        base_url=config.EVER_JOBS_API_URL,
        api_key=config.EVER_JOBS_API_KEY,
        timeout_seconds=config.REQUEST_TIMEOUT_SECONDS,
    )
    print(f"fetching EverJobs sweep ({config.EVER_JOBS_SITE_NAMES}); this takes minutes...", file=sys.stderr)
    # query/results are not honoured server-side; the sweep is everything EverJobs has.
    return client.search(query="", results=1000)


def _write_raw(jobs, now):
    out_dir = Path(os.environ.get("WAREHOUSE_RAW_DUMP_DIR", RAW_DUMP_DIR))  # same dir rotate_raw_dumps cleans
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"sweep_{now.strftime('%Y%m%dT%H%M%SZ')}.json.gz"
    with gzip.open(path, "wt") as f:
        json.dump(jobs, f)
    return path


def rotate_raw_dumps(directory, keep_days, now=None):
    """Deletes sweep_*.json.gz files older than keep_days. Returns how many went."""
    directory = Path(directory)
    if not directory.is_dir():
        return 0
    cutoff = (now or datetime.now(timezone.utc)).timestamp() - keep_days * 86400
    removed = 0
    for path in directory.glob("sweep_*.json.gz"):
        if path.stat().st_mtime < cutoff:
            path.unlink()
            removed += 1
    return removed


def main(fetch=None, now=None):
    cfg = load_pipeline_config()
    now = now or datetime.now(timezone.utc)
    jobs = (fetch or _fetch_from_everjobs)()
    raw_dir = os.environ.get("WAREHOUSE_RAW_DUMP_DIR", RAW_DUMP_DIR)
    if cfg.retention.keep_raw_dumps_days > 0:
        _write_raw(jobs, now)
    # keep_raw_dumps_days = 0 also clears any raw sweeps left from an earlier setting.
    rotate_raw_dumps(raw_dir, cfg.retention.keep_raw_dumps_days, now)
    conn = open_warehouse(os.environ.get("WAREHOUSE_DB_PATH", DEFAULT_DB_PATH))
    try:
        stats = ingest(conn, jobs, max_posted_age_days=cfg.ingest.max_posted_age_days, now=now)
        stats["purged"] = purge_warehouse(conn, cfg.retention.warehouse_retention_days, now)
    finally:
        conn.close()
    print(json.dumps({"ingested_at": now.isoformat(), **stats}))
    return stats


if __name__ == "__main__":
    main()
