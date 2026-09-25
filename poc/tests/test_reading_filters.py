"""Level / role type / hybrid need each job's reading: offered only while most jobs have one."""
import json

from jobhub_poc.webapp.app import create_app
from tests.test_matching import _seed_job


def _read(conn, jid, **fields):
    key = conn.execute("SELECT dedupe_key FROM jobs WHERE id = ?", (jid,)).fetchone()[0]
    data = {"required_skills": [], "preferred_skills": [], "min_years": None, **fields}
    conn.execute("INSERT OR REPLACE INTO job_requirements VALUES (?, ?, 'm', ?)", (key, json.dumps(data), f"t{jid}"))
    conn.commit()


def test_filters_are_hidden_and_ignored_while_few_jobs_are_read(conn):
    for jid in range(1, 6):
        _seed_job(conn, jid)
    _read(conn, 1, seniority="senior")  # the local model's reading: no work mode or role family
    client = create_app(test_conn=conn).test_client()
    page = client.get("/jobs").get_data(as_text=True)
    assert 'name="level"' not in page and 'name="role"' not in page and ">Hybrid<" not in page
    # An old link with level= would otherwise show one job of five.
    assert sum(f'id="job-{i}"' in client.get("/jobs?level=senior").get_data(as_text=True) for i in range(1, 6)) == 5
    assert client.get("/api/jobs?level=senior").get_json()["total"] == 5


def test_filters_appear_once_most_jobs_are_read(conn):
    for jid in range(1, 6):
        _seed_job(conn, jid)
        _read(conn, jid, seniority="senior" if jid == 1 else "mid", work_mode="hybrid", role_family="engineering")
    client = create_app(test_conn=conn).test_client()
    page = client.get("/jobs").get_data(as_text=True)
    assert 'name="level"' in page and 'name="role"' in page and ">Hybrid<" in page
    only = client.get("/jobs?level=senior").get_data(as_text=True)
    assert 'id="job-1"' in only and 'id="job-2"' not in only
