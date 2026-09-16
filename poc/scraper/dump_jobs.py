"""CLI: scrape EverJobs and write a timestamped, filtered JSON dump.

EverJobs' query/results fields aren't honored server-side (confirmed live
against pi05), so this fetches a site bucket ONCE, then filters/caps
client-side per configured SEARCH_TERMS -- avoiding one multi-minute,
tens-of-MB request per term.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import config
from everjobs_client import EverJobsClient


def filter_and_cap(jobs: list[dict], search_terms: list[str], results_per_term: int) -> list[dict]:
    seen_job_object_ids = set()
    picked: list[dict] = []
    for term in search_terms:
        term_lower = term.lower()
        count = 0
        for job in jobs:
            if count >= results_per_term:
                break
            title = (job.get("title") or "").lower()
            if term_lower not in title:
                continue
            key = id(job)
            if key in seen_job_object_ids:
                continue
            seen_job_object_ids.add(key)
            tagged = dict(job)
            tagged["_search_term"] = term
            picked.append(tagged)
            count += 1
    return picked


def write_dump(jobs: list[dict], dump_dir: str) -> Path:
    out_dir = Path(dump_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"dump_{timestamp}.json"
    path.write_text(json.dumps({"count": len(jobs), "jobs": jobs}, indent=2))
    return path


def main() -> None:
    client = EverJobsClient(
        base_url=config.EVER_JOBS_API_URL,
        api_key=config.EVER_JOBS_API_KEY,
        timeout_seconds=config.REQUEST_TIMEOUT_SECONDS,
    )
    print(f"fetching EverJobs bucket '{config.EVER_JOBS_SITE_NAMES}' (this can take a few minutes)...")
    all_jobs = client.search(query=" ".join(config.SEARCH_TERMS), results=1000)
    print(f"fetched {len(all_jobs)} raw job(s), filtering for {config.SEARCH_TERMS!r}")

    picked = filter_and_cap(all_jobs, config.SEARCH_TERMS, config.RESULTS_PER_TERM)
    path = write_dump(picked, config.DUMP_DIR)
    print(f"wrote {len(picked)} job(s) to {path}")


if __name__ == "__main__":
    main()
