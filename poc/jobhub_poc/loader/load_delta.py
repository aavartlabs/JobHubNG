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


TERMS_FINGERPRINT_KEY = "alert_terms_fingerprint"


def get_state(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def get_watermark(conn: sqlite3.Connection) -> str | None:
    return get_state(conn, WATERMARK_KEY)


def _set_state(conn, key, value):
    conn.execute(
        """INSERT INTO sync_state (key, value, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
        (key, value, datetime.now(timezone.utc).isoformat()),
    )


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


def load_delta(conn: sqlite3.Connection, path, watermark: str | None,
               terms_fingerprint: str | None = None) -> list[int]:
    """Returns the ids alerts should treat as new: inserted here AND first seen by the
    warehouse after the previous sync. A full re-sync (e.g. new alert terms) inserts
    warehouse jobs that are weeks old; those are loaded but not announced."""
    records = _read(path)  # parse everything before writing anything
    previous = get_watermark(conn)
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
            if inserted is not None and (previous is None or rec["first_seen_at"] > previous):
                new_ids.append(inserted)
        if watermark:
            _set_state(conn, WATERMARK_KEY, watermark)
        if terms_fingerprint is not None:
            _set_state(conn, TERMS_FINGERPRINT_KEY, terms_fingerprint)
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
    parser.add_argument("--print-terms-fingerprint", action="store_true")
    parser.add_argument("--terms-fingerprint", default=None,
                        help="alert_terms fingerprint the delta was exported with; stored on success")
    args = parser.parse_args()

    conn = db.get_connection()
    db.init_db(conn)
    if args.print_watermark:
        print(get_watermark(conn) or "")
        return
    if args.print_terms_fingerprint:
        print(get_state(conn, TERMS_FINGERPRINT_KEY) or "")
        return
    if not args.delta_path:
        parser.error("delta_path is required unless --print-watermark")
    new_ids = load_delta(conn, args.delta_path, args.watermark, args.terms_fingerprint)
    conn.close()
    print(f"loaded delta, {len(new_ids)} new job(s) inserted")
    if args.new_ids_out:
        Path(args.new_ids_out).write_text(json.dumps(new_ids))


if __name__ == "__main__":
    main()
