"""The server-rendered jobs pages: /jobs (list), /jobs/<id> (one job), /jobs/<id>/apply.
Filter/sort/paging SQL is shared with /api/jobs (jobs_listing.py); tests/test_webapp_api.py
covers it through the API, these cover what the pages add."""
import json
import re
from datetime import datetime, timedelta, timezone

import pytest

from jobhub_poc import config
from jobhub_poc.webapp.app import create_app
from jobhub_poc.webapp.jobs_listing import (
    ListQuery,
    employment_label,
    list_query_string,
    monogram,
    posted_label,
    present_job,
    safe_back_query,
    salary_label,
)

SESSION_COOKIE_NAME = "jobhub-auth.session_token"
GET_SESSION_URL = f"{config.AUTH_SERVICE_URL}/auth/get-session"


def _seed(conn, n=3, apply_url="https://employer.example/apply/{id}"):
    now = datetime.now(timezone.utc)
    for i in range(1, n + 1):
        seen = (now - timedelta(days=i)).isoformat()
        conn.execute(
            """INSERT INTO jobs (id, dedupe_key, source_site, title, company_name, location, apply_url,
                                 description, employment_type, is_remote, first_seen_at, last_seen_at, raw_json)
               VALUES (?, ?, 's', ?, 'Acme', 'Bengaluru', ?, 'Run prod.\nOn call.', 'fulltime', ?, ?, ?, '{}')""",
            (i, f"k{i}", f"SRE {i}", apply_url.format(id=i), i % 2, seen, seen),
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


def _verified(user_id="u1"):
    return {"id": user_id, "email": "a@example.com", "emailVerified": True, "telegramVerified": True}


def _interactions(conn):
    return [r["action"] for r in conn.execute("SELECT action FROM job_interactions ORDER BY id")]


# ---- /jobs ----

def test_list_is_public_and_needs_no_auth_call(conn, requests_mock):
    _seed(conn)
    resp = _client(conn).get("/jobs")
    assert resp.status_code == 200
    assert requests_mock.call_count == 0


def test_list_rows_link_to_their_job_page_and_carry_the_list_state(conn):
    _seed(conn, n=30)
    html = _client(conn).get("/jobs?q=sre&page=2&page_size=10").get_data(as_text=True)
    assert "Showing 11–20 of 30 jobs" in html
    assert 'id="job-20"' in html and 'id="job-5"' not in html  # newest first, page 2
    assert 'href="/jobs/20?back=q%3Dsre%26page%3D2%26page_size%3D10"' in html
    # Prev/Next keep the filters; page 1 is the default so it isn't in the URL.
    assert 'href="/jobs?q=sre&amp;page_size=10">← Prev' in html
    assert 'href="/jobs?q=sre&amp;page=3&amp;page_size=10">Next →' in html


def test_old_title_links_still_search():
    # ?title= was the search parameter until 2026-09-24.
    from urllib.parse import parse_qs
    assert list_query_string(ListQuery(q="sre")) == "q=sre"
    assert safe_back_query("title=sre") == "q=sre"
    assert parse_qs(safe_back_query("title=sre&q=devops")) == {"q": ["devops"]}


def test_list_shows_the_four_fields_and_no_row_buttons(conn):
    _seed(conn, n=1)
    html = _client(conn).get("/jobs").get_data(as_text=True)
    for text in ("SRE 1", "Acme", "Bengaluru", "1d ago"):
        assert text in html
    assert "Details" not in html and "Apply" not in html


def test_list_filters_keep_their_values_and_empty_results_say_so(conn):
    _seed(conn)
    html = _client(conn).get("/jobs?title=nomatch&sort=title&posted_within=7").get_data(as_text=True)
    assert "No jobs match these filters." in html
    assert 'value="nomatch"' in html
    assert re.search(r'<option value="title"\s+selected', html)
    assert re.search(r'<option value="7"\s+selected', html)


def test_page_past_the_end_shows_the_last_page(conn):
    _seed(conn, n=3)
    html = _client(conn).get("/jobs?page=99&page_size=10").get_data(as_text=True)
    assert "Showing 1–3 of 3 jobs" in html


def test_old_job_links_redirect_to_the_job_page(conn):
    resp = _client(conn).get("/jobs?job=7")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/jobs/7")


# ---- /jobs/<id> ----

def test_signed_out_sees_the_basics_and_a_sign_in_prompt_only(conn):
    _seed(conn, n=1)
    html = _client(conn).get("/jobs/1").get_data(as_text=True)
    assert "SRE 1" in html and ">Acme<" in html and "Bengaluru" in html
    assert "Run prod." not in html and "/jobs/1/apply" not in html
    assert 'href="/login?next=/jobs/1"' in html and 'href="/register?next=/jobs/1"' in html
    assert _interactions(conn) == []


def test_unverified_is_pointed_at_verification(conn, requests_mock):
    _seed(conn, n=1)
    user = {**_verified(), "telegramVerified": None}
    html = _client(conn, requests_mock, user).get("/jobs/1").get_data(as_text=True)
    assert "Run prod." not in html and 'href="/verify?next=/jobs/1"' in html


def test_verified_sees_description_and_an_apply_link_in_a_new_tab(conn, requests_mock):
    _seed(conn, n=1)
    client = _client(conn, requests_mock, _verified())
    html = client.get("/jobs/1").get_data(as_text=True)
    assert "<p>Run prod.<br>On call.</p>" in html
    assert re.search(r'href="/jobs/1/apply" target="_blank" rel="noopener"', html)
    client.get("/jobs/1")  # a repeat view within the hour is the same signal
    assert _interactions(conn) == ["view_details"]


@pytest.mark.parametrize("back, expected", [
    ("q%3Dsre%26page%3D2", "/jobs?q=sre&amp;page=2#job-1"),
    ("title%3Dsre", "/jobs?q=sre#job-1"),  # old parameter name
    ("", "/jobs#job-1"),
    ("https%3A%2F%2Fevil.example%2F", "/jobs#job-1"),          # never another site
    ("q%3Dx%26next%3D%2F%2Fevil.example", "/jobs?q=x#job-1"),  # unknown params dropped
])
def test_back_link_returns_to_the_same_list_row_and_nowhere_else(conn, back, expected):
    _seed(conn, n=1)
    html = _client(conn).get(f"/jobs/1?back={back}").get_data(as_text=True)
    assert html.count(f'href="{expected}"') >= 2  # top and bottom


def test_missing_job_is_a_friendly_404(conn):
    resp = _client(conn).get("/jobs/999")
    assert resp.status_code == 404 and "no longer listed" in resp.get_data(as_text=True)


# ---- /jobs/<id>/apply ----

def test_apply_signed_out_goes_to_login_and_comes_back_to_the_job(conn):
    _seed(conn, n=1)
    resp = _client(conn).get("/jobs/1/apply")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/login?next=/jobs/1")


def test_apply_records_the_click_then_sends_to_the_employer(conn, requests_mock):
    _seed(conn, n=1)
    resp = _client(conn, requests_mock, _verified()).get("/jobs/1/apply")
    assert resp.status_code == 302 and resp.headers["Location"] == "https://employer.example/apply/1"
    assert _interactions(conn) == ["click_apply"]


@pytest.mark.parametrize("url", ["javascript:alert(1)", "", "ftp://x.example/a"])
def test_apply_never_redirects_to_a_non_web_url(conn, requests_mock, url):
    _seed(conn, n=1, apply_url=url)
    client = _client(conn, requests_mock, _verified())
    assert client.get("/jobs/1/apply").status_code == 404
    assert "/jobs/1/apply" not in client.get("/jobs/1").get_data(as_text=True)


# ---- jobs_listing helpers ----

def test_list_query_string_leaves_defaults_out():
    assert list_query_string(ListQuery()) == ""
    assert list_query_string(ListQuery(q="sre ops", page=3)) == "q=sre+ops&page=3"
    assert list_query_string(ListQuery(work_mode="remote")) == "work_mode=remote"


def test_safe_back_query_keeps_only_valid_list_parameters():
    assert safe_back_query("q=sre&sort=posted&page=2") == "q=sre&sort=posted&page=2"
    assert safe_back_query("sort=evil&work_mode=moon&page=-1&page_size=5000&foo=bar") == "page_size=100"
    assert safe_back_query(None) == ""


def test_posted_label_prefers_the_posted_date_and_falls_back_to_first_seen():
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    assert posted_label("2026-09-21T00:00:00+00:00", "2026-09-01T00:00:00+00:00", now) == "3d ago"
    assert posted_label(None, "2026-09-10T00:00:00+00:00", now) == "seen 2w ago"
    assert posted_label(None, "2026-09-24T00:00:00+00:00", now) == "seen today"
    assert posted_label(None, "junk", now) == ""
    assert posted_label("2026-05-01", "x", now) == "4mo ago"
    assert posted_label("2021-01-01", "x", now) == "5y ago"


# ---- search, stats, the PC pane ----

def _seed_rich(conn):
    now = datetime.now(timezone.utc)
    rows = [
        # id, title, company, location, remote, first_seen (days ago), raw_json
        (1, "SRE - Site Reliability Engineer", "NVIDIA", "Pune, India", 0, 0,
         {"department": "Engineering", "compensation": {"currency": "INR", "interval": "yearly",
                                                        "minAmount": 4500000, "maxAmount": 7000000}}),
        (2, "Data Analyst", "Acme SRE Tools", "Remote", 1, 2, {"employmentType": "FULL_TIME"}),
        (3, "Chef", "Taj", "Mumbai", 0, 5, {}),
    ]
    for jid, title, company, loc, remote, days, raw in rows:
        seen = (now - timedelta(days=days, hours=1)).isoformat()
        conn.execute(
            """INSERT INTO jobs (id, dedupe_key, source_site, title, company_name, location, apply_url,
                                 description, is_remote, first_seen_at, last_seen_at, raw_json)
               VALUES (?, ?, 's', ?, ?, ?, 'https://e.example/a', 'About &amp; more', ?, ?, ?, ?)""",
            (jid, f"r{jid}", title, company, loc, remote, seen, seen, json.dumps(raw)),
        )
    conn.commit()


def test_q_matches_title_or_company_and_work_mode_filters(conn):
    _seed_rich(conn)
    html = _client(conn).get("/jobs?q=sre").get_data(as_text=True)
    assert 'id="job-1"' in html and 'id="job-2"' in html and 'id="job-3"' not in html  # company "Acme SRE Tools"
    html = _client(conn).get("/jobs?work_mode=remote").get_data(as_text=True)
    assert 'id="job-2"' in html and 'id="job-1"' not in html
    html = _client(conn).get("/jobs?work_mode=onsite").get_data(as_text=True)
    assert 'id="job-2"' not in html and 'id="job-1"' in html


def test_stats_count_every_match_not_just_the_page(conn):
    _seed_rich(conn)
    html = _client(conn).get("/jobs?page_size=10").get_data(as_text=True)
    stats = re.findall(r'<strong>([\d,]+)</strong>(Jobs found|Companies|Locations|New today)', html)
    assert dict((label, n) for n, label in stats) == {"Jobs found": "3", "Companies": "3", "Locations": "3", "New today": "1"}


def test_rows_show_real_badges_only(conn):
    _seed_rich(conn)
    html = _client(conn).get("/jobs").get_data(as_text=True)
    assert "₹45L–70L / yr" in html and "Full-time" in html and "New" in html and "Remote" in html
    for fake in ("reviews", "yrs", "Hot"):
        assert fake not in html


def test_pc_pane_shows_the_first_job_without_counting_a_view(conn, requests_mock):
    _seed_rich(conn)
    html = _client(conn, requests_mock, _verified()).get("/jobs").get_data(as_text=True)
    assert 'id="job-pane"' in html and 'data-job-panel="1"' in html
    assert re.search(r'id="job-1"[^>]*aria-current="true"', html)
    assert _interactions(conn) == []  # a phone never sees the pane


def test_sel_picks_the_pane_job_and_counts_as_a_view(conn, requests_mock):
    _seed_rich(conn)
    html = _client(conn, requests_mock, _verified()).get("/jobs?sel=3").get_data(as_text=True)
    assert 'data-job-panel="3"' in html and "About &amp; more" in html
    assert _interactions(conn) == ["view_details"]


def test_panel_fragment_is_gated_like_the_page(conn, requests_mock):
    _seed_rich(conn)
    anon = _client(conn).get("/jobs/1/panel")
    assert anon.status_code == 200 and "<html" not in anon.get_data(as_text=True)
    assert "Sign in to see the full description" in anon.get_data(as_text=True) and "About" not in anon.get_data(as_text=True)
    verified = _client(conn, requests_mock, _verified()).get("/jobs/1/panel").get_data(as_text=True)
    assert "About &amp; more" in verified and "Open full page" in verified and "/jobs/1/apply" in verified
    assert _interactions(conn) == ["view_details"]
    assert _client(conn).get("/jobs/99/panel").status_code == 404


def test_row_helpers():
    assert monogram("NVIDIA Corporation")[0] == "NV"
    assert monogram("Tata Consultancy Services")[0] == "TC"
    assert monogram("The Walt Disney Company")[0] == "WD"
    assert monogram(None)[0] == "?"
    assert monogram("Acme")[1] == monogram("ACME")[1]  # stable colour
    assert salary_label({"currency": "USD", "interval": "yearly", "minAmount": 125000, "maxAmount": 160000}) == "$125k–160k / yr"
    assert salary_label({"currency": "INR", "interval": "yearly", "minAmount": 4500000, "maxAmount": 12000000}) == "₹45L–1.2Cr / yr"
    assert salary_label({"currency": "EUR", "interval": "hourly", "minAmount": 40}) == "from €40 / hr"
    assert salary_label({"currency": "USD", "maxAmount": 90000}) == "up to $90k"
    assert salary_label({"currency": "USD"}) is None and salary_label(None) is None and salary_label("x") is None
    assert employment_label("FULL_TIME") == employment_label("Full-Time") == employment_label(["fulltime"]) == "Full-time"
    assert employment_label("contractor") == "Contract" and employment_label(None) is None and employment_label([]) is None
    assert employment_label("EOR Mexico") is None  # free text, not a job type
