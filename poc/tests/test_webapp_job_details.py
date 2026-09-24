import json

import pytest

from jobhub_poc import config
from jobhub_poc.webapp.app import create_app

SESSION_COOKIE_NAME = "jobhub-auth.session_token"
GET_SESSION_URL = f"{config.AUTH_SERVICE_URL}/auth/get-session"


def _seed_job(conn, job_id=1, dedupe_key="k1", apply_url="https://employer.example/apply/1"):
    conn.execute(
        """
        INSERT INTO jobs (id, dedupe_key, source_site, title, company_name, location, apply_url,
                          description, first_seen_at, last_seen_at, raw_json)
        VALUES (?, ?, 'acme', 'Site Reliability Engineer', 'Acme', 'Bengaluru', ?, 'Run prod.',
                '2026-09-20T00:00:00+00:00', '2026-09-20T00:00:00+00:00', '{}')
        """,
        (job_id, dedupe_key, apply_url),
    )
    conn.commit()


def _client(conn, requests_mock=None, user=None):
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    client = app.test_client()
    if user is not None:
        requests_mock.get(GET_SESSION_URL, json={"session": {}, "user": user})
        client.set_cookie(SESSION_COOKIE_NAME, "fake")
    return client


def _user(user_id="u1", email_verified=True, telegram_verified=True):
    return {"id": user_id, "email": "a@example.com", "emailVerified": email_verified,
            "telegramVerified": telegram_verified}


def _interactions(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM job_interactions ORDER BY id")]


# ---- GET /api/jobs/<id> ----

def test_details_signed_out_is_401_with_login_url_carrying_next(conn):
    _seed_job(conn)
    resp = _client(conn).get("/api/jobs/1")
    assert resp.status_code == 401
    body = resp.get_json()
    assert body["code"] == "LOGIN_REQUIRED"
    assert body["login_url"] == "/login?next=/jobs/1"
    assert "description" not in body and "apply_url" not in body
    assert _interactions(conn) == []


def test_details_unverified_is_403_pointing_at_verify(conn, requests_mock):
    _seed_job(conn)
    resp = _client(conn, requests_mock, _user(email_verified=False)).get("/api/jobs/1")
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "VERIFY_REQUIRED"
    assert resp.get_json()["verify_url"].startswith("/verify?next=")


def test_details_verified_returns_description_and_apply_url_and_logs_view(conn, requests_mock):
    _seed_job(conn)
    resp = _client(conn, requests_mock, _user()).get("/api/jobs/1")
    assert resp.status_code == 200
    job = resp.get_json()
    assert job["description"] == "Run prod."
    assert job["apply_url"] == "https://employer.example/apply/1"
    assert job["title"] == "Site Reliability Engineer"
    [row] = _interactions(conn)
    assert (row["owner_auth_user_id"], row["job_dedupe_key"], row["action"]) == ("u1", "k1", "view_details")
    assert row["job_title"] == "Site Reliability Engineer" and row["job_company"] == "Acme"


def test_repeat_views_within_an_hour_are_logged_once(conn, requests_mock):
    _seed_job(conn)
    client = _client(conn, requests_mock, _user())
    client.get("/api/jobs/1")
    client.get("/api/jobs/1")
    assert len(_interactions(conn)) == 1


def test_details_unknown_job_is_404(conn, requests_mock):
    assert _client(conn, requests_mock, _user()).get("/api/jobs/999").status_code == 404


# ---- POST /api/jobs/<id>/apply-click ----

def test_apply_click_signed_out_is_401(conn):
    _seed_job(conn)
    resp = _client(conn).post("/api/jobs/1/apply-click")
    assert resp.status_code == 401
    assert resp.get_json()["login_url"] == "/login?next=/jobs/1"


def test_apply_click_logs_and_returns_the_employer_url(conn, requests_mock):
    _seed_job(conn)
    resp = _client(conn, requests_mock, _user()).post("/api/jobs/1/apply-click")
    assert resp.status_code == 200
    assert resp.get_json() == {"apply_url": "https://employer.example/apply/1"}
    assert [r["action"] for r in _interactions(conn)] == ["click_apply"]


def test_apply_click_on_a_job_without_a_link_is_404(conn, requests_mock):
    _seed_job(conn, apply_url=None)
    assert _client(conn, requests_mock, _user()).post("/api/jobs/1/apply-click").status_code == 404
    assert _interactions(conn) == []


def test_apply_click_rejects_get(conn, requests_mock):
    _seed_job(conn)
    assert _client(conn, requests_mock, _user()).get("/api/jobs/1/apply-click").status_code == 405


def test_interactions_survive_the_job_being_purged(conn, requests_mock):
    _seed_job(conn)
    _client(conn, requests_mock, _user()).get("/api/jobs/1")
    conn.execute("DELETE FROM jobs")
    conn.commit()
    [row] = _interactions(conn)
    assert row["job_dedupe_key"] == "k1" and row["job_title"] == "Site Reliability Engineer"


# ---- login_required carries next ----

def test_gated_page_redirect_to_login_carries_next(conn):
    resp = _client(conn).get("/alerts")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login?next=/alerts")


@pytest.mark.parametrize("path", ["/jobs", "/jobs/1"])
def test_jobs_pages_themselves_stay_public(conn, path):
    _seed_job(conn)
    assert _client(conn).get(path).status_code == 200
