"""Apply a pi05 warehouse delta (scraper/export.py output) to the serving jobs table.

Each gzip JSONL line is a full record {"dedupe_key", "first_seen_at", "last_seen_at",
"search_term", "job"} or a touch {"dedupe_key", "last_seen_at", "touch": true} for a job
seen again with unchanged content. Full records are upserted through the same path as
the old dump loader, keyed by the EverJobs id, so jobs that were already here are updated
rather than re-announced as new.
The whole file -- rows and the new watermark -- is one transaction: a truncated or corrupt
delta changes nothing, and the next run re-requests from the old watermark.

    python -m jobhub_poc.loader.load_delta --print-watermark
    python -m jobhub_poc.loader.load_delta <delta.jsonl.gz> --watermark <iso> [--new-ids-out f]
"""
import argparse
import gzip
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from jobhub_poc.loader.load_dump import upsert_job

WATERMARK_KEY = "warehouse_watermark"


def get_watermark(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT value FROM sync_state WHERE key = ?", (WATERMARK_KEY,)).fetchone()
    return row["value"] if row else None


def _read(path) -> list[dict]:
    records = []
    with gzip.open(path, "rt") as f:
        for number, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}: line {number} is not valid JSON ({exc})") from None
    return records


def load_delta(conn: sqlite3.Connection, path, watermark: str | None) -> list[int]:
    """Returns the jobs.ids newly inserted (what alerts should consider)."""
    records = _read(path)  # parse everything before writing anything
    new_ids: list[int] = []
    try:
        for rec in records:
            if rec.get("touch"):
                # Seen again with unchanged content: only last_seen moves. A touch for a
                # job this DB doesn't have is skipped -- it carries no content to insert.
                conn.execute("UPDATE jobs SET last_seen_at = ? WHERE dedupe_key = ?",
                             (rec["last_seen_at"], rec["dedupe_key"]))
                continue
            inserted = upsert_job(conn, rec["job"], rec["dedupe_key"], rec["first_seen_at"],
                                  rec["last_seen_at"], rec.get("search_term"))
            if inserted is not None:
                new_ids.append(inserted)
        if watermark:
            conn.execute(
                """INSERT INTO sync_state (key, value, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
                (WATERMARK_KEY, watermark, datetime.now(timezone.utc).isoformat()),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return new_ids


def main() -> None:
    from jobhub_poc import db

    parser = argparse.ArgumentParser()
    parser.add_argument("delta_path", nargs="?")
    parser.add_argument("--watermark", default=None, help="export.py's returned watermark")
    parser.add_argument("--new-ids-out", default=None)
    parser.add_argument("--print-watermark", action="store_true")
    args = parser.parse_args()

    conn = db.get_connection()
    db.init_db(conn)
    if args.print_watermark:
        print(get_watermark(conn) or "")
        return
    if not args.delta_path:
        parser.error("delta_path is required unless --print-watermark")
    new_ids = load_delta(conn, args.delta_path, args.watermark)
    conn.close()
    print(f"loaded delta, {len(new_ids)} new job(s) inserted")
    if args.new_ids_out:
        Path(args.new_ids_out).write_text(json.dumps(new_ids))


if __name__ == "__main__":
    main()
