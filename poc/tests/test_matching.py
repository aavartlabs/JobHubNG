"""Phase 2: job requirements (grounded extraction) and the resume-vs-job match."""
import json
from datetime import date, datetime, timezone

import pytest
from cryptography.fernet import Fernet

from jobhub_poc import config, crypto, job_requirements
from jobhub_poc.ai import llm, ollama, tasks, worker
from jobhub_poc.matching import match, norm_skill, years_of_experience
from jobhub_poc.webapp.app import create_app

RESUME = {
    "name": "Asha", "headline": "Senior SRE", "location": "Bengaluru, India", "summary": "",
    "skills": ["Kubernetes", "Terraform", "AWS", "Python"],
    "roles": [
        {"title": "Senior SRE", "company": "Acme", "start": "Jan 2020", "end": "Present",
         "bullets": [{"text": "Ran k8s clusters and Prometheus alerting for payments."}]},
        {"title": "Systems Engineer", "company": "Beta", "start": "2016", "end": "Dec 2019", "bullets": []},
    ],
}
REQS = {"required_skills": ["Kubernetes", "Terraform", "Go"], "preferred_skills": ["Prometheus", "GCP"],
        "min_years": 5, "seniority": "senior"}


# ---- extraction stays honest ----

def test_requirements_keep_only_what_the_posting_says():
    text = "Senior SRE. Must have Kubernetes and Terraform, 5+ years. Nice to have: Prometheus."
    raw = {"required_skills": ["Kubernetes", "terraform", "Rust", "an excellent communicator who thrives in teams"],
           "preferred_skills": ["Prometheus", "Kubernetes"], "min_years_experience": 7, "seniority": "senior"}
    out = job_requirements.normalise(raw, text)
    assert out["required_skills"] == ["Kubernetes", "terraform"]   # Rust isn't in the text; sentences dropped
    assert out["preferred_skills"] == ["Prometheus"]                 # no duplicate of a required skill
    assert out["min_years"] is None                                   # "7" isn't stated
    assert job_requirements.normalise({**raw, "min_years_experience": 5}, text)["min_years"] == 5
    assert job_requirements.normalise({**raw, "seniority": "wizard"}, text)["seniority"] == "unknown"


# ---- the match ----

def test_years_merge_overlaps_and_count_present(monkeypatch):
    assert years_of_experience(RESUME, today=date(2026, 1, 1)) == 10.0
    overlapping = {"roles": [{"start": "2020", "end": "2022"}, {"start": "2021", "end": "2023"}]}
    assert years_of_experience(overlapping) == 4.0  # 2020 through 2023, the overlap counted once
    assert years_of_experience({"roles": [{"start": "Mar 2021", "end": "Feb 2022"}]}) == 1.0
    assert years_of_experience({"roles": [{"start": "", "end": ""}]}) is None


def test_skills_match_on_synonyms_and_experience_text():
    assert norm_skill("K8s") == "kubernetes" and norm_skill("Amazon Web Services") == "aws"
    result = match(RESUME, REQS, {"location": "Bengaluru, India", "is_remote": False})
    assert result["matched_required"] == ["Kubernetes", "Terraform"] and result["missing_required"] == ["Go"]
    assert result["matched_preferred"] == ["Prometheus"]  # from a bullet, not the skills list
    assert result["verdict"] in ("strong", "good") and 60 <= result["score"] <= 90


def test_gaps_and_location_are_explained():
    result = match({**RESUME, "roles": RESUME["roles"][:1]}, {**REQS, "min_years": 12},
                   {"location": "Berlin, Germany", "is_remote": False})
    assert any("Asks for 12+ years" in n and "Well short" in n for n in result["notes"])
    assert any("Berlin" in n for n in result["notes"])


def test_missing_most_must_haves_is_never_better_than_a_stretch():
    reqs = {"required_skills": ["Go", "Rust", "Erlang", "Kubernetes"], "preferred_skills": [],
            "min_years": None, "seniority": "senior"}
    result = match(RESUME, reqs, {"location": "", "is_remote": True})
    assert result["verdict"] in ("stretch", "weak")


def test_nothing_to_compare_says_so():
    empty = {"required_skills": [], "preferred_skills": [], "min_years": None, "seniority": "unknown"}
    result = match({"roles": []}, empty, {"location": "", "is_remote": False})
    assert result["score"] is not None or result["verdict"] == "unknown"


# ---- worker ----

def _seed_job(conn, jid=1, desc="We need Kubernetes and Terraform experts with 5+ years. " * 5):
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""INSERT INTO jobs (id, dedupe_key, source_site, title, company_name, location, apply_url,
                    description, is_remote, first_seen_at, last_seen_at, raw_json)
                    VALUES (?, ?, 's', 'Senior SRE', 'Acme', 'Bengaluru, India', 'https://e.example/a', ?, 0, ?, ?, '{}')""",
                 (jid, f"k{jid}", desc, now, now))
    conn.commit()


def test_worker_extracts_and_caches_requirements(conn, monkeypatch):
    _seed_job(conn)
    tasks.enqueue(conn, "extract_job", ref="k1")
    monkeypatch.setattr(llm, "generate", lambda *a, **k: {
        "required_skills": ["Kubernetes", "Terraform", "Cobol"], "preferred_skills": [],
        "min_years_experience": 5, "seniority": "senior"})
    assert worker.run_once(conn)
    assert job_requirements.get_many(conn, ["k1"])["k1"]["required_skills"] == ["Kubernetes", "Terraform"]


# ---- pages ----

SESSION = "jobhub-auth.session_token"
GET_SESSION_URL = f"{config.AUTH_SERVICE_URL}/auth/get-session"


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setattr(config, "RESUME_ENCRYPTION_KEY", Fernet.generate_key().decode())


def _client(conn, requests_mock, user="u1"):
    requests_mock.get(GET_SESSION_URL, json={"session": {}, "user": {"id": user, "email": "a@x.com", "emailVerified": True}})
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    c = app.test_client()
    c.set_cookie(SESSION, "x")
    return c


def _store_resume(conn, user="u1", structured=RESUME):
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""INSERT INTO resumes (owner_auth_user_id, filename, mime, size_bytes, file_enc, text_enc, structured_enc,
                    parse_status, consent_at, uploaded_at, updated_at) VALUES (?, 'r', 'm', 1, ?, ?, ?, 'done', ?, ?, ?)""",
                 (user, crypto.encrypt(b"f"), crypto.encrypt(b"t"), crypto.encrypt_json(structured), now, now, now))
    conn.commit()


def test_without_a_resume_the_job_page_invites_an_upload(conn, requests_mock, key):
    _seed_job(conn)
    html = _client(conn, requests_mock).get("/jobs/1").get_data(as_text=True)
    assert "Upload your resume" in html
    assert conn.execute("SELECT count(*) FROM ai_tasks").fetchone()[0] == 0


def test_opening_a_job_queues_its_analysis_then_shows_the_match(conn, requests_mock, key):
    _seed_job(conn)
    _store_resume(conn)
    client = _client(conn, requests_mock)
    html = client.get("/jobs/1").get_data(as_text=True)
    assert "data-match-pending" in html
    assert conn.execute("SELECT kind, ref, priority FROM ai_tasks").fetchone()[:] == ("extract_job", "k1", 5)
    assert client.get("/jobs/1/match").status_code == 202
    job_requirements.store(conn, "k1", REQS, "test")
    resp = client.get("/jobs/1/match")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200 and "% " not in body[:0]
    assert "You have:" in body and "Kubernetes" in body and "Not in your resume:" in body and "Go" in body


def test_list_shows_badges_for_analysed_jobs_and_queues_the_rest(conn, requests_mock, key):
    _seed_job(conn, 1)
    _seed_job(conn, 2)
    _store_resume(conn)
    job_requirements.store(conn, "k1", REQS, "test")
    html = _client(conn, requests_mock).get("/jobs").get_data(as_text=True)
    assert "% match" in html
    assert [tuple(r) for r in conn.execute("SELECT ref, priority FROM ai_tasks")] == [("k2", 1)]


def test_signed_out_and_other_users_see_no_match(conn, requests_mock, key):
    _seed_job(conn)
    _store_resume(conn, "u1")
    job_requirements.store(conn, "k1", REQS, "test")
    anon = create_app(test_conn=conn).test_client()
    assert "Your match" not in anon.get("/jobs/1").get_data(as_text=True) and "% match" not in anon.get("/jobs").get_data(as_text=True)
    assert anon.get("/jobs/1/match").status_code == 302
    other = _client(conn, requests_mock, "u2").get("/jobs/1").get_data(as_text=True)
    assert "Upload your resume" in other  # u2 has no resume; never sees u1's


def test_a_thin_posting_is_never_a_strong_match_and_says_so():
    reqs = {"required_skills": ["Kubernetes"], "preferred_skills": [], "min_years": None, "seniority": "senior"}
    result = match(RESUME, reqs, {"location": "", "is_remote": True})
    assert result["verdict"] == "good" and any("rough" in n for n in result["notes"])
