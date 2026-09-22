from jobhub_poc.webapp.app import create_app

# Filter/sort behavior itself is exercised against /api/jobs in
# tests/test_webapp_api.py -- these tests only cover that /jobs serves the
# shell the TypeScript bundle (static/app.js) expects to find.


def test_jobs_page_accessible_without_login(conn, requests_mock):
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    resp = app.test_client().get("/jobs")
    assert resp.status_code == 200
    # Verify no auth service calls were made
    assert requests_mock.call_count == 0


def test_jobs_page_serves_shell_with_expected_elements(conn):
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    resp = app.test_client().get("/jobs")
    assert resp.status_code == 200
    body = resp.data.decode()
    for expected_id in ("filter-form", "title-input", "location-input", "sort-select", "jobs-body"):
        assert f'id="{expected_id}"' in body
    assert "static/app.js" in body
