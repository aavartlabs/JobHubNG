"""CLI (pi05): export the warehouse rows pi09's serving DB needs, as a small gzip delta.

Selects rows seen since the caller's watermark -- changed ones in full, merely re-seen
ones as tiny "touch" records so pi09's last_seen stays exact -- whose title contains one
of the serving terms -- config/pipeline.ini [serving], later widened by active alert
terms (T14) -- and, if [serving] locations is set, whose location contains one of those.

Each output line: {"dedupe_key", "first_seen_at", "last_seen_at", "search_term", "job"}.
dedupe_key is the EverJobs id when there is one -- the same key jobhub.db has always
used -- so jobs already on pi09 are recognised, not re-announced as new.

    .venv/bin/python export.py --out /tmp/jobhub_delta.jsonl.gz [--since <ISO watermark>]
"""
import argparse
import gzip
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobhub_poc.pipeline_config import load_pipeline_config  # noqa: E402
from ingest import DEFAULT_DB_PATH  # noqa: E402
from warehouse import open_warehouse  # noqa: E402


def _first_match(text, needles):
    text = (text or "").lower()
    return next((n for n in needles if n in text), None)


def export_delta(conn, since, terms, locations, out_path, cap=0, extra_terms=()):
    """Writes the delta to out_path and returns {"exported", "touched", "watermark"}.

    With no `since` (first sync) every matching row goes in full. Otherwise rows seen since
    the watermark go in full if their content changed (updated_at > since), or else as a
    small touch record {"dedupe_key", "last_seen_at", "touch": true} that only refreshes
    pi09's last_seen. The watermark is the newest last_seen_at scanned (unchanged if none).

    extra_terms are the active alerts' titles/keywords (T14), matched against title *or*
    description, so an alert can fire on jobs the site's own search terms don't cover.
    """
    query = "SELECT * FROM jobs"
    params = ()
    if since:
        query += " WHERE last_seen_at > ?"
        params = (since,)
    query += " ORDER BY last_seen_at DESC, id"

    watermark = since
    per_term = {}
    exported = touched = 0
    with gzip.open(out_path, "wt") as out:
        for row in conn.execute(query, params):
            if watermark is None or row["last_seen_at"] > watermark:
                watermark = row["last_seen_at"]
            term = _first_match(row["title"], terms)
            if term is None and extra_terms:
                term = _first_match(f"{row['title']}\n{row['description'] or ''}", extra_terms)
            if term is None:
                continue
            if locations and not _first_match(row["location"], locations):
                continue
            if cap and per_term.get(term, 0) >= cap:
                continue
            per_term[term] = per_term.get(term, 0) + 1
            key = row["source_id"] or f"wh-{row['id']}"
            if since and row["updated_at"] <= since:
                record = {"dedupe_key": key, "last_seen_at": row["last_seen_at"], "touch": True}
                touched += 1
            else:
                record = {
                    "dedupe_key": key,
                    "first_seen_at": row["first_seen_at"],
                    "last_seen_at": row["last_seen_at"],
                    "search_term": term,
                    "job": json.loads(row["raw_json"]),
                }
                exported += 1
            out.write(json.dumps(record, separators=(",", ":")) + "\n")
    return {"exported": exported, "touched": touched, "watermark": watermark}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--since", default=None, help="ISO last_seen watermark from the last sync")
    parser.add_argument("--extra-terms-file", default=None,
                        help="JSON list of active alert terms from pi09 (alerts/alert_terms.py)")
    args = parser.parse_args(argv)

    cfg = load_pipeline_config()
    extra_terms = ()
    if args.extra_terms_file:
        with open(args.extra_terms_file) as f:
            extra_terms = tuple(str(t).lower() for t in json.load(f))
    conn = open_warehouse(os.environ.get("WAREHOUSE_DB_PATH", DEFAULT_DB_PATH))
    try:
        result = export_delta(conn, args.since or None, cfg.serving.search_terms, cfg.serving.locations,
                              args.out, cap=cfg.serving.results_per_term, extra_terms=extra_terms)
    finally:
        conn.close()
    print(json.dumps(result))
    return result


if __name__ == "__main__":
    main()
