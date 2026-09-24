"""Phase 1 of the resume features: encryption, the AI task queue and worker, reading
PDF/DOCX, keeping the structured resume honest, and the /profile routes."""
import io
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet

from jobhub_poc import config, crypto, resume_parse
from jobhub_poc.ai import ollama, tasks, worker
from jobhub_poc.resume_text import ResumeUnreadable, detect_kind, extract_text
from jobhub_poc.webapp.app import create_app

SESSION_COOKIE_NAME = "jobhub-auth.session_token"
GET_SESSION_URL = f"{config.AUTH_SERVICE_URL}/auth/get-session"

RESUME_LINES = [
    "Asha Rao",
    "Senior Site Reliability Engineer",
    "asha@example.com | +91 98765 43210",
    "Skills: Kubernetes, Terraform, AWS, Python, Prometheus",
    "Acme Pay - SRE (2021 - Present)",
    "Ran Kubernetes clusters serving 40 microservices.",
    "Cut monthly AWS spend by 22% by right-sizing EC2.",
    "Beta Corp - Systems Engineer (2017 - 2021)",
    "Built Terraform modules used by 6 teams.",
]


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setattr(config, "RESUME_ENCRYPTION_KEY", Fernet.generate_key().decode())


def _docx_bytes(lines=RESUME_LINES):
    import docx
    document = docx.Document()
    for line in lines:
        document.add_paragraph(line)
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def _pdf_bytes(lines=RESUME_LINES):
    """A minimal valid one-page PDF with real (extractable) text."""
    content = "BT /F1 11 Tf 50 780 Td 14 TL " + " ".join(
        "(" + line.replace("(", "").replace(")", "") + ") '" for line in lines) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = "%PDF-1.4\n", []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out.encode()))
        out += f"{i} 0 obj\n{body}\nendobj\n"
    xref = len(out.encode())
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    return out.encode()


# ---- encryption ----

def test_encryption_round_trips_and_needs_the_key(monkeypatch):
    token = crypto.encrypt_json({"a": "résumé"})
    assert b"sum" not in token and crypto.decrypt_json(token) == {"a": "résumé"}
    monkeypatch.setattr(config, "RESUME_ENCRYPTION_KEY", Fernet.generate_key().decode())
    with pytest.raises(crypto.CryptoUnavailable):
        crypto.decrypt(token)  # a different key can't read it
    monkeypatch.setattr(config, "RESUME_ENCRYPTION_KEY", "")
    assert crypto.enabled() is False
    monkeypatch.setattr(config, "RESUME_ENCRYPTION_KEY", "not-a-key")
    assert crypto.enabled() is False


# ---- task queue ----

def test_queue_dedupes_orders_by_priority_and_retries(conn):
    a = tasks.enqueue(conn, "parse_resume", owner="u1")
    assert tasks.enqueue(conn, "parse_resume", owner="u1") == a  # still queued: reused
    b = tasks.enqueue(conn, "extract_job", ref="k1", priority=0)
    c = tasks.enqueue(conn, "extract_job", ref="k2", priority=5)
    assert [tasks.claim(conn)["id"] for _ in range(3)] == [c, a, b]
    assert tasks.claim(conn) is None
    for attempt in range(tasks.MAX_ATTEMPTS):
        tasks.fail(conn, a, "boom")
        status = conn.execute("SELECT status FROM ai_tasks WHERE id = ?", (a,)).fetchone()[0]
        if status == "queued":
            tasks.claim(conn)
    assert conn.execute("SELECT status, error FROM ai_tasks WHERE id = ?", (a,)).fetchone()[:] == ("failed", "boom")


def test_release_keeps_the_attempt_and_stale_tasks_are_requeued(conn):
    t = tasks.enqueue(conn, "parse_resume", owner="u1")
    tasks.claim(conn)
    tasks.release(conn, t)
    assert conn.execute("SELECT status, attempts FROM ai_tasks WHERE id = ?", (t,)).fetchone()[:] == ("queued", 0)
    tasks.claim(conn)
    old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    conn.execute("UPDATE ai_tasks SET updated_at = ? WHERE id = ?", (old, t))
    assert tasks.requeue_stale(conn) == 1


# ---- reading files ----

def test_detects_by_content_not_name():
    assert detect_kind(_pdf_bytes()) == "pdf"
    assert detect_kind(_docx_bytes()) == "docx"
    assert detect_kind(b"MZ\x90\x00 an exe") is None
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("other.txt", "x")
    assert detect_kind(buf.getvalue()) is None  # a zip that isn't a Word document


@pytest.mark.parametrize("make, kind", [(_docx_bytes, "docx"), (_pdf_bytes, "pdf")])
def test_extracts_text(make, kind):
    text = extract_text(make(), kind)
    assert "Ran Kubernetes clusters serving 40 microservices." in text and "Beta Corp" in text


def test_too_little_text_is_refused():
    with pytest.raises(ResumeUnreadable, match="scanned"):
        extract_text(_docx_bytes(["Just a name"]), "docx")
    with pytest.raises(ResumeUnreadable):
        extract_text(b"%PDF-1.4 garbage", "pdf")


# ---- structured resume stays honest ----

def test_normalise_grounds_skills_flags_bullets_and_drops_contacts():
    text = "\n".join(RESUME_LINES)
    raw = {
        "name": "Asha Rao", "headline": "Senior SRE asha@example.com", "summary": "", "location": "",
        "skills": ["Kubernetes", "kubernetes", "Go", "Terraform"],  # Go isn't in the resume
        "roles": [{"title": "SRE", "company": "Acme Pay", "start": "2021", "end": "Present",
                   "bullets": ["Ran Kubernetes clusters serving 40 microservices.",
                               "Led a team of 50 engineers."]}],  # invented
        "education": [], "links": [],
    }
    out = resume_parse.normalise(raw, text)
    assert out["skills"] == ["Kubernetes", "Terraform"]
    bullets = out["roles"][0]["bullets"]
    assert [(b["id"], b["unverified"]) for b in bullets] == [("r1b1", False), ("r1b2", True)]
    assert "@" not in out["headline"]


# ---- worker ----

def _store_resume(conn, user="u1"):
    text = "\n".join(RESUME_LINES)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""INSERT INTO resumes (owner_auth_user_id, filename, mime, size_bytes, file_enc, text_enc,
                    parse_status, consent_at, uploaded_at, updated_at) VALUES (?, 'r.docx', 'x', 1, ?, ?, 'queued', ?, ?, ?)""",
                 (user, crypto.encrypt(b"file"), crypto.encrypt(text.encode()), now, now, now))
    conn.commit()
    return tasks.enqueue(conn, "parse_resume", owner=user, priority=10)


def test_worker_structures_and_stores_encrypted(conn, monkeypatch):
    task = _store_resume(conn)
    monkeypatch.setattr(ollama, "generate", lambda prompt, schema, **kw: {
        "name": "Asha Rao", "headline": "SRE", "summary": "", "skills": ["AWS"], "links": [], "education": [],
        "roles": [{"title": "SRE", "company": "Acme Pay", "start": "2021", "end": "Present",
                   "bullets": ["Cut monthly AWS spend by 22% by right-sizing EC2."]}]})
    assert worker.run_once(conn) is True
    row = conn.execute("SELECT * FROM resumes").fetchone()
    assert row["parse_status"] == "done" and b"Acme" not in row["structured_enc"]
    assert crypto.decrypt_json(row["structured_enc"])["roles"][0]["bullets"][0]["unverified"] is False
    assert conn.execute("SELECT status FROM ai_tasks WHERE id = ?", (task,)).fetchone()[0] == "done"


def test_worker_waits_when_the_llm_is_away_and_gives_up_after_errors(conn, monkeypatch):
    task = _store_resume(conn)

    def away(*a, **k):
        raise ollama.OllamaUnavailable("harita asleep")
    monkeypatch.setattr(ollama, "generate", away)
    with pytest.raises(ollama.OllamaUnavailable):
        worker.run_once(conn)
    assert conn.execute("SELECT status, attempts FROM ai_tasks WHERE id = ?", (task,)).fetchone()[:] == ("queued", 0)

    def broken(*a, **k):
        raise RuntimeError("bad json")
    monkeypatch.setattr(ollama, "generate", broken)
    while worker.run_once(conn):
        pass
    assert conn.execute("SELECT status FROM ai_tasks WHERE id = ?", (task,)).fetchone()[0] == "failed"
    assert conn.execute("SELECT parse_status FROM resumes").fetchone()[0] == "failed"


def test_ollama_client_needs_configuration(monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_URL", "")
    assert ollama.available() is False
    with pytest.raises(ollama.OllamaUnavailable):
        ollama.generate("x", {})


def test_ollama_client_parses_structured_answer(monkeypatch, requests_mock):
    monkeypatch.setattr(config, "OLLAMA_URL", "http://llm.test:11434")
    requests_mock.post("http://llm.test:11434/api/generate", json={"response": '{"ok": true}'})
    assert ollama.generate("x", {"type": "object"}) == {"ok": True}
    body = requests_mock.last_request.json()
    assert body["format"] == {"type": "object"} and body["options"]["temperature"] == 0 and body["stream"] is False
    requests_mock.post("http://llm.test:11434/api/generate", json={"response": "not json"})
    with pytest.raises(RuntimeError):
        ollama.generate("x", {})


# ---- /profile routes ----

def _client(conn, requests_mock, user_id="u1", verified=True):
    requests_mock.get(GET_SESSION_URL, json={"session": {}, "user": {
        "id": user_id, "email": "a@example.com", "emailVerified": verified, "telegramVerified": None}})
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    client = app.test_client()
    client.set_cookie(SESSION_COOKIE_NAME, "fake")
    return client


def _upload(client, data=None, consent=True, name="cv.docx"):
    form = {"resume": (io.BytesIO(data if data is not None else _docx_bytes()), name)}
    if consent:
        form["consent"] = "on"
    return client.post("/profile/resume", data=form, content_type="multipart/form-data")


def test_profile_needs_a_signed_in_verified_user(conn, requests_mock):
    app = create_app(test_conn=conn)
    assert app.test_client().get("/profile").status_code == 302
    assert "/verify" in _client(conn, requests_mock, verified=False).get("/profile").headers["Location"]


def test_upload_stores_only_ciphertext_and_queues_parsing(conn, requests_mock):
    client = _client(conn, requests_mock)
    assert _upload(client).status_code == 302
    row = conn.execute("SELECT * FROM resumes WHERE owner_auth_user_id = 'u1'").fetchone()
    assert row["parse_status"] == "queued" and row["filename"] == "cv.docx"
    assert b"Kubernetes" not in row["text_enc"] and b"PK" not in row["file_enc"][:4]
    assert "Kubernetes" in crypto.decrypt(row["text_enc"]).decode()
    assert conn.execute("SELECT kind, owner_auth_user_id, priority FROM ai_tasks").fetchone()[:] == ("parse_resume", "u1", 10)
    assert "Reading your resume" in client.get("/profile").get_data(as_text=True) or \
        "offline" in client.get("/profile").get_data(as_text=True)


@pytest.mark.parametrize("kwargs, message", [
    ({"consent": False}, "confirm you agree"),
    ({"data": b"hello, not a document", "name": "cv.pdf"}, "PDF or Word"),
    ({"data": b""}, "Choose a PDF"),
])
def test_bad_uploads_are_refused(conn, requests_mock, kwargs, message):
    resp = _upload(_client(conn, requests_mock), **kwargs)
    assert resp.status_code == 400 and message in resp.get_data(as_text=True)
    assert conn.execute("SELECT count(*) FROM resumes").fetchone()[0] == 0


def test_oversized_upload_is_refused(conn, requests_mock, monkeypatch):
    monkeypatch.setattr(config, "MAX_RESUME_BYTES", 1000)
    resp = _upload(_client(conn, requests_mock))
    assert resp.status_code in (400, 413)
    assert conn.execute("SELECT count(*) FROM resumes").fetchone()[0] == 0


def test_over_the_request_limit_gets_the_profile_page_not_a_bare_413(conn, requests_mock):
    client = _client(conn, requests_mock)
    client.application.config["MAX_CONTENT_LENGTH"] = 2000
    resp = _upload(client, data=b"%PDF-" + b"x" * 5000, name="big.pdf")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 413 and "Your resume" in body and "is over" in body


def test_limit_is_5_mb_and_the_form_carries_it(conn, requests_mock):
    assert config.MAX_RESUME_BYTES == 5 * 1024 * 1024
    assert f'data-max-bytes="{5 * 1024 * 1024}"' in _client(conn, requests_mock).get("/profile").get_data(as_text=True)


def test_upload_is_off_without_a_key(conn, requests_mock, monkeypatch):
    monkeypatch.setattr(config, "RESUME_ENCRYPTION_KEY", "")
    client = _client(conn, requests_mock)
    assert _upload(client).status_code == 503
    assert "aren't switched on" in client.get("/profile").get_data(as_text=True)


def test_review_form_saves_edits_and_keeps_flags_honest(conn, requests_mock, monkeypatch):
    client = _client(conn, requests_mock)
    _upload(client)
    monkeypatch.setattr(ollama, "generate", lambda *a, **k: {
        "name": "Asha", "headline": "SRE", "summary": "", "skills": ["AWS"], "links": [], "education": [],
        "roles": [{"title": "SRE", "company": "Acme Pay", "start": "2021", "end": "Present",
                   "bullets": ["Ran Kubernetes clusters serving 40 microservices.", "Invented bullet."]}]})
    worker.run_once(conn)
    page = client.get("/profile").get_data(as_text=True)
    assert "Check your details" in page and "found word-for-word in your file" in page
    assert "to check" in page and 'id="sec-role-0"' in page
    resp = client.post("/profile/resume/save", data={
        "name": "Asha Rao", "headline": "Senior SRE", "location": "", "summary": "", "skills": "AWS, Kubernetes, aws",
        "role_count": "1",
        "role-0-title": "SRE", "role-0-company": "Acme Pay", "role-0-start": "2021", "role-0-end": "Present",
        "role-0-bullets": "Ran Kubernetes clusters serving 40 microservices.\nInvented bullet.\nMy own new line.",
        "role-1-title": "Engineer", "role-1-company": "Beta Corp", "role-1-bullets": "Built Terraform modules used by 6 teams.",
        "education": "B.Tech, NIT", "links": ""})
    assert resp.status_code == 302
    s = crypto.decrypt_json(conn.execute("SELECT structured_enc FROM resumes").fetchone()[0])
    assert s["skills"] == ["AWS", "Kubernetes"] and [r["company"] for r in s["roles"]] == ["Acme Pay", "Beta Corp"]
    assert [(b["text"], b["unverified"]) for b in s["roles"][0]["bullets"]] == [
        ("Ran Kubernetes clusters serving 40 microservices.", False), ("Invented bullet.", True), ("My own new line.", False)]


def test_download_and_status_are_owner_only_and_delete_purges(conn, requests_mock):
    mine = _client(conn, requests_mock, "u1")
    data = _docx_bytes()
    _upload(mine, data)
    resp = mine.get("/profile/resume/file")
    assert resp.data == data and resp.headers["Cache-Control"] == "no-store"
    task_id = conn.execute("SELECT id FROM ai_tasks").fetchone()[0]
    assert mine.get(f"/ai/tasks/{task_id}").status_code == 200
    other = _client(conn, requests_mock, "u2")
    assert other.get(f"/ai/tasks/{task_id}").status_code == 404
    assert other.get("/profile/resume/file").status_code == 302  # u2 has none
    mine = _client(conn, requests_mock, "u1")
    mine.post("/profile/resume/delete")
    assert conn.execute("SELECT count(*) FROM resumes").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM ai_tasks").fetchone()[0] == 0


def test_a_resume_under_a_lost_key_is_reported_not_a_500(conn, requests_mock, monkeypatch):
    client = _client(conn, requests_mock)
    _upload(client)
    conn.execute("UPDATE resumes SET structured_enc = ?", (crypto.encrypt_json({"name": "x", "roles": []}),))
    conn.commit()
    monkeypatch.setattr(config, "RESUME_ENCRYPTION_KEY", Fernet.generate_key().decode())  # the key changed
    page = client.get("/profile")
    assert page.status_code == 200 and "read your stored resume any more" in page.get_data(as_text=True)
    assert client.get("/profile/resume/file").status_code == 302
    assert _upload(client).status_code == 302  # a fresh upload replaces it
    assert "read your stored resume any more" not in client.get("/profile").get_data(as_text=True)


def test_consent_is_asked_once(conn, requests_mock):
    client = _client(conn, requests_mock)
    _upload(client)
    first = conn.execute("SELECT consent_at FROM resumes").fetchone()[0]
    page = client.get("/profile").get_data(as_text=True)
    assert 'name="consent" value="on"' in page and "You agreed to how we use your resume" in page
    assert _upload(client, consent=False).status_code == 302  # a new version needs no new tick
    assert conn.execute("SELECT consent_at FROM resumes").fetchone()[0] == first
