"""api_sources.py: Adzuna and Careerjet mapped to EverJobs' job shape, and never fatal."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import api_sources
from api_sources import ADZUNA_URL, CAREERJET_URL, fetch_all
from warehouse import ingest, open_warehouse

CFG = SimpleNamespace(enabled=("adzuna", "careerjet"), queries=("developer", "data engineer", "tester"),
                      adzuna_country="in", adzuna_requests_per_run=2, careerjet_locale="en_IN",
                      careerjet_location="India", careerjet_requests_per_run=5, delay_ms=0)
ENV = {"ADZUNA_APP_ID": "a-id", "ADZUNA_APP_KEY": "a-key", "CAREERJET_AFFID": "cj", "CAREERJET_USER_IP": "203.0.113.9"}
ADZUNA = {"results": [{"id": "4711", "title": "Java Developer", "company": {"display_name": "Infosys"},
                       "location": {"display_name": "Wanowarie, Maharashtra", "area": ["India", "Maharashtra", "Pune", "Wanowarie"]},
                       "description": "Build Java services...", "redirect_url": "https://www.adzuna.in/land/ad/4711",
                       "created": "2026-09-25T08:00:00Z", "contract_time": "full_time"}]}
CAREERJET = {"type": "JOBS", "hits": 1, "jobs": [{"title": "Data Engineer (Remote)", "company": "Razorpay",
             "locations": "Bengaluru, Karnataka", "description": "Spark and Kafka...", "url": "https://jobviewtrack.com/x1",
             "date": "Fri, 25 Sep 2026 10:00:00 GMT"}]}


def test_adzuna_and_careerjet_become_everjobs_shaped_jobs(requests_mock):
    requests_mock.get(ADZUNA_URL.format(country="in"), json=ADZUNA)
    requests_mock.get(CAREERJET_URL, json=CAREERJET)
    jobs, stats = fetch_all(CFG, env=ENV, sleep=lambda s: None)
    a = next(j for j in jobs if j["site"] == "adzuna")
    assert a["id"] == "adzuna-4711" and a["companyName"] == "Infosys"
    assert a["location"] == {"country": "India", "state": "Maharashtra", "city": "Pune"}
    assert a["applyUrl"] == "https://www.adzuna.in/land/ad/4711" and a["datePosted"] == "2026-09-25T08:00:00Z"
    c = next(j for j in jobs if j["site"] == "careerjet")
    assert c["id"].startswith("careerjet-") and c["location"] == {"city": "Bengaluru", "state": "Karnataka", "country": "India"}
    assert c["datePosted"] == "2026-09-25T10:00:00+00:00" and c["isRemote"] is True
    assert stats["adzuna"]["requests"] == 2 and stats["careerjet"]["requests"] == 3  # capped per run / all queries
    cj = [r for r in requests_mock.request_history if r.url.startswith(CAREERJET_URL)][0]
    assert cj.headers["Referer"] == api_sources.REFERER and cj.qs["locale_code"] == ["en_in"] and cj.qs["user_ip"] == ["203.0.113.9"]


def test_missing_keys_rejected_keys_and_failures_are_never_fatal(requests_mock):
    jobs, stats = fetch_all(CFG, env={}, sleep=lambda s: None)
    assert jobs == [] and "missing" in stats["adzuna"]["skipped"] and "missing" in stats["careerjet"]["skipped"]
    requests_mock.get(ADZUNA_URL.format(country="in"), status_code=401)
    requests_mock.get(CAREERJET_URL, [{"status_code": 500}, {"json": CAREERJET}, {"json": {"type": "ERROR", "error": "quota"}}])
    jobs, stats = fetch_all(CFG, env=ENV, sleep=lambda s: None)
    assert stats["adzuna"] == {"requests": 1, "jobs": 0, "errors": 0, "stopped": "adzuna: HTTP 401"}
    assert stats["careerjet"]["errors"] == 1 and stats["careerjet"]["jobs"] == 1 and "quota" in stats["careerjet"]["stopped"]
    assert "a-key" not in str(stats)  # an error never carries the key (it's in the URL)


def test_api_jobs_merge_with_the_same_job_from_a_company_page(tmp_path):
    conn = open_warehouse(str(tmp_path / "wh.db"))
    now = datetime(2026, 9, 26, 6, 0, tzinfo=timezone.utc)
    page = {"id": "infosys-1", "site": "infosys", "title": "Java Developer", "companyName": "Infosys",
            "location": {"city": "Pune", "state": "Maharashtra", "country": "India"}, "description": "Full posting",
            "jobUrl": "https://careers.infosys.com/1", "datePosted": "2026-09-25"}
    stats = ingest(conn, [page, api_sources_job()], max_posted_age_days=60, now=now)
    assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1 and stats["duplicates"] == 1


def api_sources_job():
    return {"id": "adzuna-4711", "site": "adzuna", "title": "Java Developer", "companyName": "Infosys",
            "location": {"country": "India", "state": "Maharashtra", "city": "Pune"}, "description": "Build...",
            "jobUrl": "https://www.adzuna.in/land/ad/4711", "datePosted": "2026-09-25T08:00:00Z"}


def test_ingest_adds_the_api_jobs_to_the_sweep_and_reports_them(tmp_path, monkeypatch, capsys):
    import ingest as cli
    monkeypatch.setenv("WAREHOUSE_DB_PATH", str(tmp_path / "wh.db"))
    stats = cli.main(fetch=lambda: [], now=datetime(2026, 9, 26, 6, 0, tzinfo=timezone.utc),
                     fetch_sources=lambda cfg: ([api_sources_job()], {"adzuna": {"requests": 1, "jobs": 1, "errors": 0}}))
    assert stats["inserted"] == 1 and stats["sources"]["adzuna"]["jobs"] == 1
    assert '"sources": {"adzuna"' in capsys.readouterr().out

    def broken(cfg):
        raise RuntimeError("boom")
    stats = cli.main(fetch=lambda: [], now=datetime(2026, 9, 26, 6, 0, tzinfo=timezone.utc), fetch_sources=broken)
    assert stats["sources"] == {"error": "RuntimeError"}  # the sweep still went in
