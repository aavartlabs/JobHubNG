import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from everjobs_client import EverJobsClient, EverJobsError


def test_search_posts_expected_payload_and_headers_and_parses_jobs(requests_mock):
    requests_mock.post(
        "http://localhost:3001/api/jobs/search",
        json={"jobs": [{"id": "1", "site": "acme", "title": "Software Engineer", "companyName": "Acme"}]},
    )
    client = EverJobsClient(base_url="http://localhost:3001", api_key="k", timeout_seconds=5)
    jobs = client.search(query="software engineer", results=5)
    assert jobs == [{"id": "1", "site": "acme", "title": "Software Engineer", "companyName": "Acme"}]

    sent = requests_mock.request_history[0]
    assert sent.headers["x-api-key"] == "k"
    assert sent.json() == {"input": {"query": "software engineer", "results": 5}}


def test_search_without_api_key_omits_header(requests_mock):
    requests_mock.post("http://localhost:3001/api/jobs/search", json={"jobs": []})
    client = EverJobsClient(base_url="http://localhost:3001", api_key=None, timeout_seconds=5)
    client.search(query="x", results=1)
    assert "x-api-key" not in requests_mock.request_history[0].headers


def test_search_missing_jobs_key_returns_empty_list(requests_mock):
    requests_mock.post("http://localhost:3001/api/jobs/search", json={"count": 0})
    client = EverJobsClient(base_url="http://localhost:3001", timeout_seconds=5)
    assert client.search(query="x", results=1) == []


def test_search_non_200_raises_everjobs_error(requests_mock):
    requests_mock.post("http://localhost:3001/api/jobs/search", status_code=500, text="boom")
    client = EverJobsClient(base_url="http://localhost:3001", timeout_seconds=5)
    try:
        client.search(query="x", results=1)
        assert False, "expected EverJobsError"
    except EverJobsError as e:
        assert "500" in str(e)


def test_search_timeout_raises_everjobs_error(requests_mock):
    import requests
    requests_mock.post("http://localhost:3001/api/jobs/search", exc=requests.exceptions.Timeout)
    client = EverJobsClient(base_url="http://localhost:3001", timeout_seconds=5)
    try:
        client.search(query="x", results=1)
        assert False, "expected EverJobsError"
    except EverJobsError:
        pass
