import pytest

from jobhub_poc import config
from jobhub_poc.webapp.app import create_app


@pytest.fixture
def client(conn, monkeypatch):
    monkeypatch.setattr(config, "WEB_ORIGIN", "https://jobshub.example.com")
    monkeypatch.setattr(config, "LEGACY_HOSTS", {"jobhubs.example.com"})
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    return app.test_client()


def test_old_host_redirects_permanently_to_the_same_page(client):
    resp = client.get("/jobs?job=12&x=1", headers={"Host": "jobhubs.example.com"})
    assert resp.status_code == 301
    assert resp.headers["Location"] == "https://jobshub.example.com/jobs?job=12&x=1"


def test_path_without_query_has_no_trailing_question_mark(client):
    resp = client.get("/alerts", headers={"Host": "jobhubs.example.com"})
    assert resp.headers["Location"] == "https://jobshub.example.com/alerts"


def test_non_get_requests_keep_their_method(client):
    resp = client.post("/auth/sign-in/email", headers={"Host": "jobhubs.example.com"})
    assert resp.status_code == 308
    assert resp.headers["Location"] == "https://jobshub.example.com/auth/sign-in/email"


def test_host_matching_ignores_port_and_case(client):
    resp = client.get("/jobs", headers={"Host": "JobHubs.Example.com:443"})
    assert resp.status_code == 301


def test_current_host_is_served_normally(client):
    assert client.get("/jobs", headers={"Host": "jobshub.example.com"}).status_code == 200
