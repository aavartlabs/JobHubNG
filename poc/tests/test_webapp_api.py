import json

from jobhub_poc.webapp.app import create_app


def _seed_job(conn, dedupe_key, title, location, first_seen_at, company_name="Acme",
               apply_url=None, description=None):
    conn.execute(
        """
        INSERT INTO jobs (dedupe_key, source_site, title, company_name, location, apply_url,
                           description, first_seen_at, last_seen_at, raw_json)
        VALUES (?, 'acme', ?, ?, ?, ?, ?, ?, ?, '{}')
        """,
        (dedupe_key, title, company_name, location, apply_url, description, first_seen_at, first_seen_at),
    )
    conn.commit()


def test_api_jobs_accessible_without_login(conn, requests_mock):
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    resp = app.test_client().get("/api/jobs")
    assert resp.status_code == 200
    # Verify no auth service calls were made
    assert requests_mock.call_count == 0


def test_api_jobs_returns_json_shape(conn):
    _seed_job(conn, "1", "Software Engineer", "Remote", "2026-09-16T10:00:00+00:00",
              apply_url="https://example.com/1", description="Build great things.")
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    resp = app.test_client().get("/api/jobs")
    assert resp.status_code == 200
    assert resp.content_type.startswith("application/json")
    data = json.loads(resp.data)
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["total_pages"] == 1
    job = data["jobs"][0]
    assert job["title"] == "Software Engineer"
    assert job["company_name"] == "Acme"
    assert job["location"] == "Remote"
    assert job["apply_url"] == "https://example.com/1"
    assert job["description"] == "Build great things."
    assert "first_seen_at" in job


def test_api_jobs_description_is_null_when_missing(conn):
    _seed_job(conn, "1", "Software Engineer", "Remote", "2026-09-16T10:00:00+00:00")
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    resp = app.test_client().get("/api/jobs")
    data = json.loads(resp.data)
    assert data["jobs"][0]["description"] is None


def test_api_jobs_title_filter(conn):
    _seed_job(conn, "1", "Senior Data Engineer", "Remote", "2026-09-16T10:00:00+00:00")
    _seed_job(conn, "2", "Sales Associate", "Remote", "2026-09-16T09:00:00+00:00")
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    resp = app.test_client().get("/api/jobs?title=engineer")
    data = json.loads(resp.data)
    titles = [j["title"] for j in data["jobs"]]
    assert titles == ["Senior Data Engineer"]


def test_api_jobs_location_filter(conn):
    _seed_job(conn, "1", "Engineer", "Bengaluru, India", "2026-09-16T10:00:00+00:00")
    _seed_job(conn, "2", "Engineer", "Remote", "2026-09-16T09:00:00+00:00")
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    resp = app.test_client().get("/api/jobs?location=bengaluru")
    data = json.loads(resp.data)
    assert len(data["jobs"]) == 1
    assert "Bengaluru" in data["jobs"][0]["location"]


def test_api_jobs_default_sort_is_freshness_descending(conn):
    _seed_job(conn, "1", "Older Job", "Remote", "2026-09-14T10:00:00+00:00")
    _seed_job(conn, "2", "Newer Job", "Remote", "2026-09-16T10:00:00+00:00")
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    resp = app.test_client().get("/api/jobs")
    data = json.loads(resp.data)
    titles = [j["title"] for j in data["jobs"]]
    assert titles == ["Newer Job", "Older Job"]


def test_api_jobs_sort_title_ascending(conn):
    _seed_job(conn, "1", "Zebra Role", "Remote", "2026-09-16T10:00:00+00:00")
    _seed_job(conn, "2", "Alpha Role", "Remote", "2026-09-16T09:00:00+00:00")
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    resp = app.test_client().get("/api/jobs?sort=title")
    data = json.loads(resp.data)
    titles = [j["title"] for j in data["jobs"]]
    assert titles == ["Alpha Role", "Zebra Role"]


def _seed_n_jobs(conn, n):
    for i in range(n):
        _seed_job(conn, str(i), f"Role {i:03d}", "Remote", f"2026-09-16T{10 + (i % 10):02d}:00:00+00:00")


def test_api_jobs_pagination_respects_page_size(conn):
    _seed_n_jobs(conn, 25)
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    resp = app.test_client().get("/api/jobs?page_size=10")
    data = json.loads(resp.data)
    assert len(data["jobs"]) == 10
    assert data["total"] == 25
    assert data["page"] == 1
    assert data["page_size"] == 10
    assert data["total_pages"] == 3


def test_api_jobs_pagination_second_page_has_different_rows(conn):
    _seed_n_jobs(conn, 25)
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    client = app.test_client()
    page1 = json.loads(client.get("/api/jobs?page_size=10&page=1&sort=title").data)
    page2 = json.loads(client.get("/api/jobs?page_size=10&page=2&sort=title").data)
    ids_page1 = {j["id"] for j in page1["jobs"]}
    ids_page2 = {j["id"] for j in page2["jobs"]}
    assert ids_page1.isdisjoint(ids_page2)
    assert len(page2["jobs"]) == 10


def test_api_jobs_pagination_last_page_partial(conn):
    _seed_n_jobs(conn, 25)
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    resp = app.test_client().get("/api/jobs?page_size=10&page=3")
    data = json.loads(resp.data)
    assert len(data["jobs"]) == 5


def test_api_jobs_total_reflects_filter_not_just_current_page(conn):
    _seed_job(conn, "1", "Engineer One", "Remote", "2026-09-16T10:00:00+00:00")
    _seed_job(conn, "2", "Engineer Two", "Remote", "2026-09-16T09:00:00+00:00")
    _seed_job(conn, "3", "Sales Associate", "Remote", "2026-09-16T08:00:00+00:00")
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    resp = app.test_client().get("/api/jobs?title=engineer&page_size=1")
    data = json.loads(resp.data)
    assert data["total"] == 2
    assert data["total_pages"] == 2
    assert len(data["jobs"]) == 1


def test_api_jobs_page_size_is_capped(conn):
    _seed_n_jobs(conn, 5)
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    resp = app.test_client().get("/api/jobs?page_size=99999")
    data = json.loads(resp.data)
    assert data["page_size"] <= 100


def test_api_jobs_invalid_page_defaults_to_one(conn):
    _seed_n_jobs(conn, 5)
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    resp = app.test_client().get("/api/jobs?page=not-a-number")
    data = json.loads(resp.data)
    assert data["page"] == 1
