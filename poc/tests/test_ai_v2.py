"""AI v2: Jev decides (job reading, match evidence), Muse drafts, code keeps it honest."""
import json
import re
from datetime import datetime, timedelta, timezone

import pytest
import requests
from cryptography.fernet import Fernet

from jobhub_poc import config, crypto, job_reading, job_requirements, match_evidence, matching
from jobhub_poc.ai import llm, tasks, typesafe, worker
from jobhub_poc.loader import purge
from tests.test_matching import RESUME, _client, _seed_job, _store_resume

JEV = typesafe.URL
POSTING = ("Senior SRE at Acme. Must have: Kubernetes and Terraform, 5+ years. Nice to have: Prometheus. "
           "You'll work alongside our Salesforce team. Hybrid in Bengaluru. ") * 3


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setattr(config, "RESUME_ENCRYPTION_KEY", Fernet.generate_key().decode())


@pytest.fixture
def jev(monkeypatch, requests_mock):
    """A stand-in Jev: answers by the skill named in each question, records what it was sent."""
    monkeypatch.setattr(config, "TYPESAFE_API_KEY", "ts-key")
    uses = {"kubernetes": "required", "terraform": "required", "prometheus": "preferred",
            "salesforce": "mentioned", "rust": "absent"}
    levels = {"kubernetes": 3.0, "terraform": 2.0, "prometheus": 1.0}
    sent = []

    def reply(request, context):
        body = request.json()
        sent.append(body)
        answers = {}
        for qid, q in body["questions"].items():
            named = (re.search(r"“(.+?)”", q.get("instructions", "")) or [None, ""])[1].lower()
            if qid.startswith("skill_"):
                use = uses.get(named, "absent")
                answers[qid] = {"type": "choice", "choice": use, "confidence": 0.9, "probabilities": {use: 0.9}}
            elif qid == "min_years":
                answers[qid] = {"type": "choice", "choice": "y5" if "y5" in q["criteria"] else "not_stated",
                                "confidence": 0.9, "probabilities": {"y5": 0.9}}
            elif qid.startswith("evidence_"):
                answers[qid] = {"type": "score", "score": levels.get(named, 0.0), "confidence": 0.8}
            elif qid.startswith("line_"):
                pick = "r1b1" if named == "kubernetes" and "r1b1" in q["criteria"] else "none"
                answers[qid] = {"type": "choice", "choice": pick, "confidence": 0.9}
            elif q["type"] == "noul":
                answers[qid] = {"type": "noul", "noul": 0.9}
            else:
                pick = {"seniority": "senior", "work_mode": "hybrid", "employment": "full_time",
                        "role_family": "engineering", "seniority_fit": "fit"}.get(qid, "unknown")
                answers[qid] = {"type": "choice", "choice": pick, "confidence": 0.9, "probabilities": {pick: 0.9}}
        return {"model": "jev-test", "answers": answers, "usage": {"input_tokens": 10}}

    requests_mock.post(JEV, json=reply)
    return sent


def _draft(monkeypatch, skills=("Kubernetes", "Terraform", "Rust", "Salesforce")):
    monkeypatch.setattr(llm, "generate", lambda *a, **k: {
        "required_skills": list(skills), "preferred_skills": ["Prometheus"],
        "min_years_experience": 5, "seniority": "senior"})
    monkeypatch.setattr(llm, "model_name", lambda: "meta/muse-test")


# ---- the Jev client ----

def test_jev_client_sends_state_and_questions_and_maps_errors(monkeypatch, requests_mock):
    monkeypatch.setattr(config, "TYPESAFE_API_KEY", "")
    with pytest.raises(typesafe.TypeSafeUnavailable):
        typesafe.ask("s", {"q": {"type": "noul", "instructions": "?"}})
    monkeypatch.setattr(config, "TYPESAFE_API_KEY", "ts-key")
    requests_mock.post(JEV, json={"answers": {"q": {"type": "noul", "noul": 0.7}}})
    assert typesafe.ask({"a": 1}, {"q": {"type": "noul", "instructions": "?"}}) == {"q": {"type": "noul", "noul": 0.7}}
    body = requests_mock.last_request.json()
    assert body["model"] == "jev-latest" and body["state"] == {"a": 1}
    assert requests_mock.last_request.headers["Authorization"] == "Bearer ts-key"
    for status in (429, 529, 503, 401):  # busy or a key problem: the task waits
        requests_mock.post(JEV, status_code=status, text="no")
        with pytest.raises(typesafe.TypeSafeUnavailable):
            typesafe.ask("s", {"q": {}})
    requests_mock.post(JEV, exc=requests.ConnectionError("down"))
    with pytest.raises(typesafe.TypeSafeUnavailable) as err:
        typesafe.ask("s", {"q": {}})
    assert "ts-key" not in str(err.value)
    requests_mock.post(JEV, status_code=422, text="bad question")
    with pytest.raises(RuntimeError) as err:
        typesafe.ask("s", {"q": {}})
    assert not isinstance(err.value, llm.Unavailable)
    requests_mock.post(JEV, json={"answers": {}})
    with pytest.raises(RuntimeError, match="didn't answer"):
        typesafe.ask("s", {"q": {}})


# ---- job reading: Muse drafts, Jev decides ----

def test_jev_decides_what_the_draft_proposed(conn, monkeypatch, jev):
    _draft(monkeypatch)
    data, model = job_reading.read(conn, "Senior SRE", POSTING)
    assert data["required_skills"] == ["Kubernetes", "Terraform"]  # Rust: not in the posting; Salesforce: only mentioned
    assert data["preferred_skills"] == ["Prometheus"]
    assert (data["min_years"], data["seniority"], data["work_mode"], data["role_family"]) == (5, "senior", "hybrid", "engineering")
    assert model == "jev+meta/muse-test"
    asked = [q["instructions"] for q in jev[0]["questions"].values() if "“" in q.get("instructions", "")]
    assert not any("Rust" in a for a in asked)  # a draft skill the posting doesn't contain is never even asked about
    assert list(jev[0]["questions"]["min_years"]["criteria"]) == ["y5", "not_stated"]  # only numbers the text states


def test_confirmed_skills_become_candidates_for_later_postings(conn, monkeypatch, jev):
    _draft(monkeypatch)
    job_reading.read(conn, "Senior SRE", POSTING)
    _draft(monkeypatch, skills=())  # the next draft misses them...
    data, _ = job_reading.read(conn, "Senior SRE", POSTING)
    assert set(data["required_skills"]) == {"Kubernetes", "Terraform"}  # ...the vocabulary doesn't
    assert conn.execute("SELECT skill FROM skills_vocab WHERE skill = 'salesforce'").fetchone() is None


def test_job_reading_falls_back_when_either_model_is_down(conn, monkeypatch, requests_mock, jev):
    _draft(monkeypatch)
    requests_mock.post(JEV, status_code=503)  # Jev down: Muse's draft, grounded, as before
    data, model = job_reading.read(conn, "Senior SRE", POSTING)
    assert model == "meta/muse-test" and "Rust" not in data["required_skills"]

    def down(*a, **k):
        raise llm.Unavailable("all writers down")
    monkeypatch.setattr(llm, "generate", down)
    with pytest.raises(llm.Unavailable):  # both down: the task waits
        job_reading.read(conn, "Senior SRE", POSTING)


def test_the_worker_stores_the_jev_reading(conn, monkeypatch, jev):
    _seed_job(conn, desc=POSTING)
    _draft(monkeypatch)
    tasks.enqueue(conn, "extract_job", ref="k1")
    assert worker.run_once(conn)
    row = conn.execute("SELECT data_json, model FROM job_requirements").fetchone()
    assert json.loads(row[0])["work_mode"] == "hybrid" and row[1].startswith("jev+")


# ---- match evidence: Jev judges the resume, code scores ----

def test_matching_uses_evidence_levels_seniority_fit_and_field():
    reqs = {"required_skills": ["Kubernetes", "Terraform", "Go"], "preferred_skills": ["Prometheus"],
            "min_years": None, "seniority": "senior"}
    evidence = {"skills": {"Kubernetes": {"level": 3.0, "line": "r1b1", "line_text": "Ran k8s clusters."},
                           "Terraform": {"level": 1.0, "line": None, "line_text": None},
                           "Go": {"level": 0.0, "line": None, "line_text": None},
                           "Prometheus": {"level": 2.0, "line": None, "line_text": None}},
                "seniority_fit": "fit", "same_field": 0.9}
    job = {"location": "", "is_remote": True}
    result = matching.match(RESUME, reqs, job, evidence)
    assert result["matched_required"] == ["Kubernetes"] and result["missing_required"] == ["Terraform", "Go"]
    assert result["lines"] == {"Kubernetes": "Ran k8s clusters."} and result["judged"]
    assert any("not shown in a role: Terraform" in n for n in result["notes"])
    assert result["parts"]["required"] == pytest.approx((1.0 + 0.4 + 0.0) / 3)
    other_field = matching.match(RESUME, reqs, job, {**evidence, "same_field": 0.05})
    assert other_field["verdict"] in ("stretch", "weak") and any("different kind of work" in n for n in other_field["notes"])
    assert matching.match(RESUME, reqs, job)["judged"] is False  # no evidence: literal matching, as before


def test_jev_sees_the_work_history_but_never_the_name_or_contact():
    state = match_evidence.state_for_jev({**RESUME, "contact": "a@x.com", "links": ["https://me.example"]},
                                         {"required_skills": ["Go"]}, "SRE")
    dumped = json.dumps(state)
    assert "Asha" not in dumped and "a@x.com" not in dumped and "me.example" not in dumped and "Bengaluru" not in dumped
    assert "Senior SRE" in dumped and "Kubernetes" in dumped


def _resume_with_ids():
    return {**RESUME, "roles": [{**RESUME["roles"][0], "bullets": [{"id": "r1b1", "text": "Ran k8s clusters for payments."}]}]}


def test_match_is_queued_judged_stored_encrypted_and_shown_with_the_users_line(conn, requests_mock, key, monkeypatch, jev):
    _seed_job(conn, desc=POSTING)
    _store_resume(conn, structured=_resume_with_ids())
    job_requirements.store(conn, "k1", {"required_skills": ["Kubernetes", "Terraform"], "preferred_skills": ["Prometheus"],
                                        "min_years": 5, "seniority": "senior"}, "jev")
    client = _client(conn, requests_mock)
    assert "data-match-pending" in client.get("/jobs/1").get_data(as_text=True)
    assert conn.execute("SELECT kind, owner_auth_user_id, ref FROM ai_tasks").fetchone()[:] == ("match", "u1", "k1")
    assert worker.run_once(conn)
    stored = conn.execute("SELECT data_enc FROM match_evidence").fetchone()[0]
    assert b"Kubernetes" not in stored and b"k8s" not in stored  # encrypted at rest
    body = client.get("/jobs/1/match").get_data(as_text=True)
    assert "Ran k8s clusters for payments." in body and "weighed skill by skill" in body
    assert "Asha" not in json.dumps(jev[-1])  # never the name

    # An edited resume invalidates the judgment: judged again.
    edited = {**_resume_with_ids(), "skills": ["Kubernetes", "Go"]}
    conn.execute("UPDATE resumes SET structured_enc = ?", (crypto.encrypt_json(edited),))
    conn.commit()
    assert client.get("/jobs/1/match").status_code == 202


def test_no_jev_or_stale_consent_means_plain_matching_and_nothing_sent(conn, requests_mock, key, monkeypatch):
    _seed_job(conn)
    _store_resume(conn)
    job_requirements.store(conn, "k1", {"required_skills": ["Kubernetes"], "preferred_skills": [], "min_years": None,
                                        "seniority": "senior"}, "jev")
    client = _client(conn, requests_mock)
    monkeypatch.setattr(config, "TYPESAFE_API_KEY", "")
    assert client.get("/jobs/1/match").status_code == 200  # no Jev: literal now
    monkeypatch.setattr(config, "TYPESAFE_API_KEY", "ts-key")
    conn.execute("UPDATE resumes SET consent_at = '2026-01-01T00:00:00+00:00'")
    conn.commit()
    assert client.get("/jobs/1/match").status_code == 200  # old consent: never sent to Jev
    assert conn.execute("SELECT COUNT(*) FROM ai_tasks WHERE kind = 'match'").fetchone()[0] == 0


def test_deleting_the_resume_deletes_its_match_evidence(conn, requests_mock, key):
    _seed_job(conn)
    _store_resume(conn)
    match_evidence.store(conn, "u1", "k1", RESUME, {"required_skills": []}, {"skills": {}}, "jev")
    _client(conn, requests_mock).post("/profile/resume/delete")
    assert conn.execute("SELECT COUNT(*) FROM match_evidence").fetchone()[0] == 0


# ---- storage hygiene ----

def test_tidy_drops_old_activity_and_rows_for_gone_jobs(conn, key):
    _seed_job(conn)
    now = datetime.now(timezone.utc)
    old, recent = (now - timedelta(days=40)).isoformat(), now.isoformat()
    conn.executemany("INSERT INTO ai_tasks (kind, ref, status, attempts, created_at, updated_at) VALUES (?, ?, ?, 1, ?, ?)",
                     [("extract_job", "k1", "done", old, old), ("extract_job", "k1", "queued", old, old),
                      ("extract_job", "k1", "done", recent, recent)])
    conn.executemany("INSERT INTO job_interactions (owner_auth_user_id, job_dedupe_key, action, created_at) VALUES ('u1', 'k1', 'view_details', ?)",
                     [((now - timedelta(days=200)).isoformat(),), (recent,)])
    match_evidence.store(conn, "u1", "gone-job", RESUME, {}, {"skills": {}}, "jev")
    match_evidence.store(conn, "u1", "k1", RESUME, {}, {"skills": {}}, "jev")
    job_requirements.store(conn, "gone-job", {}, "jev")
    counts = purge.tidy(conn)
    assert counts == {"ai_tasks": 1, "job_interactions": 1, "match_evidence": 1, "job_requirements": 1}
    assert conn.execute("SELECT status FROM ai_tasks WHERE updated_at = ?", (old,)).fetchone()[0] == "queued"  # waiting work stays


def test_every_unread_listed_job_is_queued_once_in_the_background(conn):
    from jobhub_poc.ai import queue_reads
    _seed_job(conn, 1)
    _seed_job(conn, 2)
    _seed_job(conn, 3, desc="short")
    job_requirements.store(conn, "k1", {}, "jev")
    assert queue_reads.queue(conn) == 1
    assert queue_reads.queue(conn) == 1  # still unread, but not queued twice
    assert [tuple(r) for r in conn.execute("SELECT ref, priority FROM ai_tasks")] == [("k2", 0)]
