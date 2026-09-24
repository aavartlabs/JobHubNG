"""job_links: links people can open, and the loader keeping derived data honest."""
import json

import pytest

from jobhub_poc.job_links import human_url, smartrecruiters_api
from jobhub_poc.loader.load_dump import upsert_job


@pytest.mark.parametrize("url, expected", [
    ("https://api.smartrecruiters.com/v1/companies/TurnerTownsend/postings/744000151582544",
     "https://jobs.smartrecruiters.com/TurnerTownsend/744000151582544"),
    ("http://API.smartrecruiters.com/v1/companies/Achieve1/postings/37439/", "https://jobs.smartrecruiters.com/Achieve1/37439"),
    ("https://api.smartrecruiters.com/v1/companies/X/postings/1?lang=en", "https://jobs.smartrecruiters.com/X/1"),
    ("https://jobs.smartrecruiters.com/X/1-lead-engineer", "https://jobs.smartrecruiters.com/X/1-lead-engineer"),
    ("https://api.smartrecruiters.com/v1/companies/X", "https://api.smartrecruiters.com/v1/companies/X"),
    ("https://builtin.com/job/staff-designer/1", "https://builtin.com/job/staff-designer/1"),
    ("", ""), (None, None),
])
def test_human_url(url, expected):
    assert human_url(url) == expected


def test_smartrecruiters_api_parts():
    assert smartrecruiters_api("https://api.smartrecruiters.com/v1/companies/C/postings/9") == ("C", "9")
    assert smartrecruiters_api(123) is None


def _job(**extra):
    job = {"id": "sr-1", "title": "Lead Data Engineer", "companyName": "T&T",
           "jobUrl": "https://api.smartrecruiters.com/v1/companies/C/postings/9", "datePosted": "2026-09-24"}
    job.update(extra)
    return job


def test_the_loader_stores_the_human_link_and_rereads_changed_descriptions(conn):
    now = "2026-09-24T12:00:00+00:00"
    upsert_job(conn, _job(), "sr-1", now, now)
    assert conn.execute("SELECT apply_url FROM jobs").fetchone()[0] == "https://jobs.smartrecruiters.com/C/9"
    conn.execute("INSERT INTO job_requirements VALUES ('sr-1', ?, 'm', ?)", (json.dumps({"required_skills": []}), now))
    upsert_job(conn, _job(), "sr-1", now, now)                                   # same text: analysis kept
    assert conn.execute("SELECT count(*) FROM job_requirements").fetchone()[0] == 1
    upsert_job(conn, _job(description="Job Description:\n<p>Databricks</p>"), "sr-1", now, now)
    assert conn.execute("SELECT count(*) FROM job_requirements").fetchone()[0] == 0
