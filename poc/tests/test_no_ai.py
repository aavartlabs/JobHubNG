"""The no-AI freeze (AI_PAUSED=1): AI results are hidden for everyone and nothing is queued
for AI; search, "Jobs for you" from saved preferences, saved jobs and the tracker still work."""
import json

import pytest

from jobhub_poc import config
from tests.test_ai_v2 import key  # noqa: F401 -- the encryption-key fixture
from tests.test_matching import _client, _seed_job, _store_resume

READING = {"required_skills": ["Kubernetes", "Terraform"], "preferred_skills": [], "min_years": 5, "seniority": "senior"}


@pytest.fixture
def paused(monkeypatch):
    monkeypatch.setattr(config, "AI_PAUSED", True)


def _read(conn, jid=1):
    conn.execute("INSERT INTO job_requirements VALUES (?, ?, 'm', 'x')", (f"k{jid}", json.dumps(READING)))
    conn.commit()


def _ai_tasks(conn):
    return conn.execute("SELECT COUNT(*) FROM ai_tasks").fetchone()[0]


def test_with_ai_on_the_resume_holder_sees_match_results(conn, requests_mock, key):  # noqa: F811
    _seed_job(conn)
    _read(conn)
    _store_resume(conn)
    client = _client(conn, requests_mock)
    page = client.get("/jobs/1").get_data(as_text=True)
    assert "match-card" in page and "Tailor my resume" in page


def test_ai_results_are_hidden_and_nothing_is_queued(conn, requests_mock, key, paused):  # noqa: F811
    _seed_job(conn)
    _seed_job(conn, 2)
    _read(conn)
    _store_resume(conn)
    client = _client(conn, requests_mock)
    listing = client.get("/jobs?all=1").get_data(as_text=True)
    page = client.get("/jobs/1").get_data(as_text=True)
    assert 'id="job-1"' in listing and 'id="job-2"' in listing
    assert "match-card" not in page and "match-card" not in listing and "Tailor my resume" not in page
    assert "Your application" not in page  # nothing to show until they apply
    assert _ai_tasks(conn) == 0  # job 2 has no reading: not queued either
    assert client.get("/jobs/1/match").status_code == 404
    for path in ("/jobs/1/tailor", "/profile/resume.docx", "/profile/print"):
        assert client.get(path).status_code == 404, path
    assert client.post("/jobs/1/tailor").status_code == 404


def test_the_tracker_still_works(conn, requests_mock, key, paused):  # noqa: F811
    _seed_job(conn)
    client = _client(conn, requests_mock)
    client.get("/jobs/1/apply")
    page = client.get("/jobs/1").get_data(as_text=True)
    assert "Your application" in page and "Did you apply?" in page


def test_profile_keeps_preferences_and_the_file_but_not_the_ai_resume(conn, requests_mock, key, paused):  # noqa: F811
    _store_resume(conn)
    client = _client(conn, requests_mock)
    page = client.get("/profile").get_data(as_text=True)
    assert "Your profile" in page and "Resume features are paused" in page
    assert 'id="preferences"' in page and "download" in page and "Delete my resume" in page
    assert "Save details" not in page and 'name="resume"' not in page  # no AI-read resume, no upload
    before = conn.execute("SELECT updated_at FROM resumes").fetchone()[0]
    resp = client.post("/profile/resume", data={"consent": "on"})
    assert resp.status_code == 503
    assert conn.execute("SELECT updated_at FROM resumes").fetchone()[0] == before and _ai_tasks(conn) == 0


def test_jobs_for_you_from_saved_preferences_without_a_resume(conn, requests_mock, paused):
    _seed_job(conn)
    _seed_job(conn, 2)
    conn.execute("UPDATE jobs SET title = 'Data Engineer', location = 'Pune, India' WHERE id = 2")
    conn.commit()
    client = _client(conn, requests_mock)
    assert 'id="preferences"' in client.get("/profile").get_data(as_text=True)  # the form, with no resume
    assert client.post("/profile/preferences", data={"roles": "Data Engineer", "locations": "Pune"}).status_code == 302
    page = client.get("/jobs").get_data(as_text=True)
    assert "Jobs for you:" in page and 'id="job-2"' in page and 'id="job-1"' not in page
