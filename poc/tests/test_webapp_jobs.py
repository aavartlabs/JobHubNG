from jobhub_poc import config
from jobhub_poc.webapp.app import create_app

SESSION_COOKIE_NAME = "jobhub-auth.session_token"
GET_SESSION_URL = f"{config.AUTH_SERVICE_URL}/auth/get-session"


def _verified_user():
    return {
        "id": "auth-user-1",
        "email": "seeker@example.com",
        "name": "Job Seeker",
        "emailVerified": True,
        "phoneNumberVerified": True,
        "phoneNumber": "+15551234567",
    }


def _logged_in_client(conn, requests_mock):
    requests_mock.get(GET_SESSION_URL, json={"session": {}, "user": _verified_user()})
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    client = app.test_client()
    client.set_cookie(SESSION_COOKIE_NAME, "fake-session-token")
    return client


# Filter/sort behavior itself is exercised against /api/jobs in
# tests/test_webapp_api.py -- these tests only cover that /jobs serves the
# shell the TypeScript bundle (static/app.js) expects to find.


def test_jobs_page_requires_login(conn):
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    resp = app.test_client().get("/jobs")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_jobs_page_serves_shell_with_expected_elements(conn, requests_mock):
    client = _logged_in_client(conn, requests_mock)
    resp = client.get("/jobs")
    assert resp.status_code == 200
    body = resp.data.decode()
    for expected_id in ("filter-form", "title-input", "location-input", "sort-select", "jobs-body"):
        assert f'id="{expected_id}"' in body
    assert "static/app.js" in body
