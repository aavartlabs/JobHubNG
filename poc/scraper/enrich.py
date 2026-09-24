"""CLI (pi05): fill in what EverJobs leaves out, between ingest and export.

Today that is SmartRecruiters: EverJobs gives those jobs no description and the Posting
API's URL as their link (a page of JSON). The Posting API is public -- the same URL,
fetched here once per posting -- and has the ad's sections and the posting's own page.
What is found goes to the warehouse's enrichments table and is laid over the job
(warehouse.overlay), now and on every later sweep.

Polite by design: only jobs in the latest sweep, at most [enrich] max_per_run a run, a
pause between fetches, a failed fetch retried only after retry_after_days, and a 429
ends the run. Never fatal to the pipeline: errors are counted, not raised.

    .venv/bin/python enrich.py
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobhub_poc.job_links import smartrecruiters_api  # noqa: E402
from jobhub_poc.pipeline_config import load_pipeline_config  # noqa: E402
from ingest import DEFAULT_DB_PATH  # noqa: E402
from warehouse import open_warehouse, refresh_enriched  # noqa: E402

API = "https://api.smartrecruiters.com/v1/companies/{company}/postings/{posting}"
USER_AGENT = "JobsHub/1.0 (+https://jobshub.aavartlabs.com)"
# The ad's own sections first; the employer's boilerplate "about us" last.
_SECTIONS = ("jobDescription", "qualifications", "additionalInformation", "companyDescription")


class RateLimited(RuntimeError):
    pass


def description_from(posting):
    """The posting's sections as one description: a "Title:" line, then the section's HTML
    (the web app's job_text.format_description renders both safely)."""
    sections = ((posting.get("jobAd") or {}).get("sections")) or {}
    parts = []
    for key in _SECTIONS:
        section = sections.get(key) or {}
        text = (section.get("text") or "").strip()
        if text:
            title = (section.get("title") or "").strip().rstrip(":")
            parts.append(f"{title}:\n{text}" if title else text)
    return "\n\n".join(parts)


def fetch_posting(company, posting, session=None, timeout=15):
    """("ok", description, page URL) | ("gone", None, None). Raises RateLimited on 429 and
    requests/RuntimeError on anything else unexpected (an "error" to retry later)."""
    resp = (session or requests).get(API.format(company=company, posting=posting), timeout=timeout,
                                     headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    if resp.status_code in (404, 410):
        return "gone", None, None
    if resp.status_code == 429:
        raise RateLimited("429 from SmartRecruiters")
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}")
    data = resp.json()
    if data.get("active") is False:
        return "gone", None, None
    description = description_from(data)
    if not description:
        raise RuntimeError("posting has no description sections")
    page = data.get("postingUrl") or f"https://jobs.smartrecruiters.com/{company}/{posting}"
    return "ok", description, page


def candidates(conn, retry_after_days, now, first_terms=()):
    """(source_id, company, posting id) for SmartRecruiters jobs in the latest sweep that
    have no description and no enrichment worth keeping (ok / gone / a recent error).
    Jobs whose title contains one of `first_terms` (the site's [serving] search terms --
    what export.py sends to pi09) come first, newest first: the per-run cap is spent on
    jobs people can actually see."""
    latest = conn.execute("SELECT max(last_seen_at) FROM jobs").fetchone()[0]
    if latest is None:
        return []
    retry_before = (now - timedelta(days=retry_after_days)).isoformat()
    rows = conn.execute(
        """SELECT j.source_id, j.title, j.raw_json FROM jobs j LEFT JOIN enrichments e ON e.source_id = j.source_id
           WHERE j.last_seen_at = ? AND j.source_id IS NOT NULL AND COALESCE(TRIM(j.description), '') = ''
             AND (e.source_id IS NULL OR (e.status = 'error' AND e.fetched_at < ?))
           ORDER BY j.first_seen_at DESC""", (latest, retry_before)).fetchall()
    shown, rest = [], []
    for row in rows:
        raw = json.loads(row["raw_json"])
        parts = smartrecruiters_api(raw.get("jobUrl")) or smartrecruiters_api(raw.get("applyUrl"))
        if parts:
            title = (row["title"] or "").lower()
            (shown if any(t in title for t in first_terms) else rest).append((row["source_id"], *parts))
    return shown + rest


def _record(conn, source_id, status, description=None, apply_url=None, error=None, now=None):
    conn.execute(
        """INSERT INTO enrichments (source_id, source, status, description, apply_url, error, fetched_at)
           VALUES (?, 'smartrecruiters', ?, ?, ?, ?, ?)
           ON CONFLICT (source_id) DO UPDATE SET status = excluded.status, description = excluded.description,
             apply_url = excluded.apply_url, error = excluded.error, fetched_at = excluded.fetched_at""",
        (source_id, status, description, apply_url, (error or "")[:300] or None, now.isoformat()))


def enrich(conn, max_per_run, retry_after_days, delay_ms, now=None, fetch=fetch_posting, sleep=time.sleep,
           first_terms=()):
    now = now or datetime.now(timezone.utc)
    todo = candidates(conn, retry_after_days, now, first_terms)
    stats = {"candidates": len(todo), "fetched": 0, "ok": 0, "gone": 0, "errors": 0, "updated": 0,
             "rate_limited": False}
    session = requests.Session()
    for i, (source_id, company, posting) in enumerate(todo[:max_per_run]):
        if i and delay_ms:
            sleep(delay_ms / 1000)
        stats["fetched"] += 1
        try:
            status, description, page = fetch(company, posting, session=session)
        except RateLimited:
            stats["rate_limited"] = True
            break
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            with conn:
                _record(conn, source_id, "error", error=str(exc), now=now)
            stats["errors"] += 1
            continue
        with conn:  # one job at a time: a crash keeps what was done
            _record(conn, source_id, status, description, page, now=now)
            if status == "ok" and refresh_enriched(conn, source_id, now):
                stats["updated"] += 1
        stats[status] += 1
    return stats


def main():
    cfg = load_pipeline_config()
    conn = open_warehouse(os.environ.get("WAREHOUSE_DB_PATH", DEFAULT_DB_PATH))
    try:
        stats = enrich(conn, cfg.enrich.max_per_run, cfg.enrich.retry_after_days, cfg.enrich.delay_ms,
                       first_terms=cfg.serving.search_terms)
    finally:
        conn.close()
    print(json.dumps(stats))
    return stats


if __name__ == "__main__":
    main()
