"""enrich.py: SmartRecruiters jobs get their description and a human link, once, politely,
and later sweeps of the same bare EverJobs record don't count as changes."""
import gzip
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import enrich  # noqa: E402
from export import export_delta  # noqa: E402
from warehouse import ingest, open_warehouse  # noqa: E402

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
API_URL = "https://api.smartrecruiters.com/v1/companies/TurnerTownsend/postings/744000151582544"


def _sr_job(job_id="tt-744000151582544", url=API_URL, **extra):
    job = {"id": job_id, "title": "Lead Data Engineer", "companyName": "Turner & Townsend", "site": "turnertownsend",
           "location": {"city": "Madrid", "country": "es"}, "datePosted": "2026-09-24", "jobUrl": url,
           "isRemote": False, "atsType": "smartrecruiters"}
    job.update(extra)
    return job


POSTING = {
    "active": True,
    "postingUrl": "https://jobs.smartrecruiters.com/TurnerTownsend/744000151582544-lead-data-engineer",
    "jobAd": {"sections": {
        "companyDescription": {"title": "Company Description", "text": "<p>We build things.</p>"},
        "jobDescription": {"title": "Job Description", "text": "<p>Design pipelines.</p><ul><li>Databricks</li></ul>"},
        "qualifications": {"title": "Qualifications", "text": "<ul><li>8-10 years of data engineering</li></ul>"},
        "additionalInformation": {"title": "Additional Information", "text": ""},
    }},
}


@pytest.fixture
def conn(tmp_path):
    c = open_warehouse(tmp_path / "warehouse.db")
    yield c
    c.close()


def _fake(result):
    calls = []

    def fetch(company, posting, session=None):
        calls.append((company, posting))
        if isinstance(result, Exception):
            raise result
        return result
    fetch.calls = calls
    return fetch


def test_the_description_keeps_the_ads_sections_in_order():
    text = enrich.description_from(POSTING)
    assert text.index("Job Description:") < text.index("Qualifications:") < text.index("Company Description:")
    assert "Additional Information" not in text and "<li>Databricks</li>" in text


def test_a_posting_is_fetched_once_and_its_job_updated_and_exported(conn, tmp_path):
    ingest(conn, [_sr_job(), _sr_job("other-1", url="https://jobs.example/1", description="Has one.")],
           max_posted_age_days=60, now=NOW)
    fetch = _fake(("ok", enrich.description_from(POSTING), POSTING["postingUrl"]))
    stats = enrich.enrich(conn, 10, 7, 0, now=NOW + timedelta(minutes=1), fetch=fetch)
    assert fetch.calls == [("TurnerTownsend", "744000151582544")]
    assert stats == {"candidates": 1, "fetched": 1, "ok": 1, "gone": 0, "errors": 0, "updated": 1, "rate_limited": False}
    row = conn.execute("SELECT * FROM jobs WHERE source_id = 'tt-744000151582544'").fetchone()
    assert "Design pipelines" in row["description"] and row["apply_url"] == POSTING["postingUrl"]
    assert conn.execute("SELECT count(*) FROM job_versions").fetchone()[0] == 1

    out = tmp_path / "d.jsonl.gz"
    export_delta(conn, (NOW - timedelta(hours=6)).isoformat(), ("engineer",), (), out)
    sent = [json.loads(line) for line in gzip.open(out, "rt")]
    assert sent[0]["job"]["description"].startswith("Job Description:") and sent[0]["job"]["_enriched"] == "smartrecruiters"

    # Nothing left to do on the next run.
    assert enrich.enrich(conn, 10, 7, 0, now=NOW, fetch=_fake(None))["candidates"] == 0


def test_the_next_sweeps_bare_record_is_not_a_change(conn):
    ingest(conn, [_sr_job()], max_posted_age_days=60, now=NOW)
    enrich.enrich(conn, 10, 7, 0, now=NOW, fetch=_fake(("ok", "Job Description:\n<p>x</p>", POSTING["postingUrl"])))
    again = ingest(conn, [_sr_job()], max_posted_age_days=60, now=NOW + timedelta(hours=6))
    assert again["unchanged"] == 1 and again["updated"] == 0
    assert conn.execute("SELECT description FROM jobs").fetchone()[0] == "Job Description:\n<p>x</p>"
    # ...but a record that later arrives with its own description wins.
    ingest(conn, [_sr_job(description="From EverJobs.")], max_posted_age_days=60, now=NOW + timedelta(hours=12))
    assert conn.execute("SELECT description FROM jobs").fetchone()[0] == "From EverJobs."


def test_links_become_human_even_without_a_fetch(conn):
    ingest(conn, [_sr_job()], max_posted_age_days=60, now=NOW)
    assert conn.execute("SELECT apply_url FROM jobs").fetchone()[0] == \
        "https://jobs.smartrecruiters.com/TurnerTownsend/744000151582544"


def test_gone_errors_retry_window_cap_and_rate_limit(conn):
    jobs = [_sr_job(f"sr-{i}", url=f"https://api.smartrecruiters.com/v1/companies/C/postings/{i}", title=f"Engineer {i}")
            for i in range(5)]
    ingest(conn, jobs, max_posted_age_days=60, now=NOW)
    assert enrich.enrich(conn, 2, 7, 0, now=NOW, fetch=_fake(("gone", None, None)))["gone"] == 2   # cap
    assert enrich.enrich(conn, 10, 7, 0, now=NOW, fetch=_fake(RuntimeError("HTTP 503")))["errors"] == 3
    assert enrich.enrich(conn, 10, 7, 0, now=NOW + timedelta(days=1), fetch=_fake(None))["candidates"] == 0
    limited = enrich.enrich(conn, 10, 7, 0, now=NOW + timedelta(days=8), fetch=_fake(enrich.RateLimited()))
    assert limited["rate_limited"] is True and limited["candidates"] == 3 and limited["errors"] == 0
    statuses = dict(conn.execute("SELECT status, count(*) FROM enrichments GROUP BY status").fetchall())
    assert statuses == {"gone": 2, "error": 3}


def test_fetch_posting_reads_the_api(requests_mock):
    requests_mock.get(API_URL, json=POSTING)
    status, description, page = enrich.fetch_posting("TurnerTownsend", "744000151582544")
    assert status == "ok" and "Qualifications:" in description and page == POSTING["postingUrl"]
    assert requests_mock.last_request.headers["User-Agent"].startswith("JobsHub/")
    requests_mock.get(API_URL, json={**POSTING, "active": False})
    assert enrich.fetch_posting("TurnerTownsend", "744000151582544")[0] == "gone"
    requests_mock.get(API_URL, status_code=404)
    assert enrich.fetch_posting("TurnerTownsend", "744000151582544")[0] == "gone"
    requests_mock.get(API_URL, status_code=429)
    with pytest.raises(enrich.RateLimited):
        enrich.fetch_posting("TurnerTownsend", "744000151582544")


def test_jobs_the_site_shows_are_fetched_first(conn):
    jobs = [_sr_job("sr-a", url="https://api.smartrecruiters.com/v1/companies/C/postings/1", title="Warehouse Picker"),
            _sr_job("sr-b", url="https://api.smartrecruiters.com/v1/companies/C/postings/2", title="Data Engineer")]
    ingest(conn, jobs, max_posted_age_days=60, now=NOW)
    fetch = _fake(("gone", None, None))
    enrich.enrich(conn, 1, 7, 0, now=NOW, fetch=fetch, first_terms=("engineer",))
    assert fetch.calls == [("C", "2")]


def test_a_repost_under_a_new_id_is_enriched_under_the_id_its_record_carries(conn):
    """The same job reposted under a new EverJobs id folds into the first row by
    fingerprint; the stored record (and every later sweep) carries the new id."""
    ingest(conn, [_sr_job("tt-1")], max_posted_age_days=60, now=NOW)
    repost = _sr_job("tt-2", url="https://api.smartrecruiters.com/v1/companies/TurnerTownsend/postings/2")
    ingest(conn, [repost], max_posted_age_days=60, now=NOW + timedelta(hours=6))
    assert conn.execute("SELECT source_id FROM jobs").fetchone()[0] == "tt-1"
    fetch = _fake(("ok", "Job Description:\n<p>x</p>", "https://jobs.smartrecruiters.com/TurnerTownsend/2-x"))
    stats = enrich.enrich(conn, 10, 7, 0, now=NOW + timedelta(hours=6), fetch=fetch)
    assert fetch.calls == [("TurnerTownsend", "2")] and stats["updated"] == 1
    assert conn.execute("SELECT description FROM jobs").fetchone()[0] == "Job Description:\n<p>x</p>"
    again = ingest(conn, [repost], max_posted_age_days=60, now=NOW + timedelta(hours=12))
    assert again["unchanged"] == 1
