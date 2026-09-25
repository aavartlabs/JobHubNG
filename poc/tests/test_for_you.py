"""'Jobs for you': the default /jobs for a signed-in user with a resume."""
from jobhub_poc import job_preferences
from tests.test_matching import _client, _seed_job, _store_resume
from tests.test_ai_v2 import key  # noqa: F401 -- the encryption-key fixture

RESUME = {"name": "A", "headline": "Senior SRE", "location": "Bengaluru, India", "skills": ["Kubernetes"],
          "roles": [{"title": "Site Reliability Engineer", "company": "X", "start": "2020", "end": "Present", "bullets": []}]}


def _job(conn, jid, title, location, remote=0):
    _seed_job(conn, jid)
    conn.execute("UPDATE jobs SET title = ?, location = ?, is_remote = ? WHERE id = ?", (title, location, remote, jid))
    conn.commit()


def test_proposal_from_the_resume_and_title_family():
    prefs = job_preferences.propose(RESUME)
    assert prefs == {"roles": ["sre", "site reliability engineer"], "locations": ["bengaluru"], "include_remote": True}
    terms = job_preferences.title_terms(prefs["roles"])
    assert "devops" in terms and "platform engineer" in terms


def test_jobs_opens_on_jobs_for_you_and_can_show_all(conn, requests_mock, key):  # noqa: F811
    _job(conn, 1, "DevOps Engineer", "Bengaluru, Karnataka")
    _job(conn, 2, "Sales Manager", "Bengaluru, Karnataka")
    _job(conn, 3, "SRE", "Austin, TX")
    _job(conn, 4, "Platform Engineer", "Anywhere", remote=1)
    _store_resume(conn, structured=RESUME)
    client = _client(conn, requests_mock)
    page = client.get("/jobs").get_data(as_text=True)
    assert "Jobs for you:" in page and 'id="job-1"' in page and 'id="job-4"' in page
    assert 'id="job-2"' not in page and 'id="job-3"' not in page
    everything = client.get("/jobs?all=1").get_data(as_text=True)
    assert all(f'id="job-{i}"' in everything for i in (1, 2, 3, 4)) and "Jobs for you:" not in everything
    typed = client.get("/jobs?q=Sales").get_data(as_text=True)
    assert 'id="job-2"' in typed and "Jobs for you:" not in typed


def test_saved_preferences_replace_the_proposal(conn, requests_mock, key):  # noqa: F811
    _job(conn, 1, "Data Engineer", "Pune, India")
    _job(conn, 2, "DevOps Engineer", "Bengaluru")
    _store_resume(conn, structured=RESUME)
    client = _client(conn, requests_mock)
    assert client.post("/profile/preferences", data={"roles": "Data Engineer", "locations": "Pune"}).status_code == 302
    page = client.get("/jobs").get_data(as_text=True)
    assert 'id="job-1"' in page and 'id="job-2"' not in page


def test_signed_out_users_see_the_list_as_before(conn):
    from jobhub_poc.webapp.app import create_app
    _job(conn, 1, "Sales Manager", "Austin, TX")
    page = create_app(test_conn=conn).test_client().get("/jobs").get_data(as_text=True)
    assert 'id="job-1"' in page and "Jobs for you:" not in page
