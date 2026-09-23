import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warehouse import fingerprint, ingest, open_warehouse

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


def _job(job_id="acme-1", title="Site Reliability Engineer", company="Acme", city="Bengaluru",
         posted="2026-09-20", site="acme", **extra):
    job = {
        "id": job_id, "title": title, "companyName": company, "site": site,
        "location": {"city": city, "state": "KA", "country": "in"} if city else None,
        "datePosted": posted, "jobUrl": f"https://jobs.example/{job_id}", "isRemote": False,
        "description": "Run production.", "employmentType": "Full-time",
    }
    job.update(extra)
    return job


@pytest.fixture
def conn(tmp_path):
    c = open_warehouse(tmp_path / "warehouse.db")
    yield c
    c.close()


def _rows(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM jobs ORDER BY id")]


def test_new_jobs_are_inserted_with_parsed_fields_and_raw_json(conn):
    stats = ingest(conn, [_job()], max_posted_age_days=60, now=NOW)
    assert stats["inserted"] == 1
    [row] = _rows(conn)
    assert row["source_id"] == "acme-1"
    assert row["title"] == "Site Reliability Engineer"
    assert row["company_name"] == "Acme"
    assert row["location"] == "Bengaluru, KA, in"
    assert row["apply_url"] == "https://jobs.example/acme-1"
    assert row["posted_at"] == "2026-09-20T00:00:00+00:00"
    assert row["first_seen_at"] == row["last_seen_at"] == row["updated_at"] == NOW.isoformat()
    assert json.loads(row["raw_json"])["id"] == "acme-1"


def test_seeing_a_job_again_bumps_last_seen_and_updated_at_but_not_first_seen(conn):
    ingest(conn, [_job()], max_posted_age_days=60, now=NOW)
    later = NOW + timedelta(hours=6)
    stats = ingest(conn, [_job(description="Run production. Now with on-call.")], max_posted_age_days=60, now=later)
    assert stats == {**stats, "inserted": 0, "updated": 1}
    [row] = _rows(conn)
    assert row["first_seen_at"] == NOW.isoformat()
    assert row["last_seen_at"] == row["updated_at"] == later.isoformat()
    assert row["description"] == "Run production. Now with on-call."


def test_same_job_on_two_sites_is_stored_once(conn):
    stats = ingest(conn, [
        _job("acme-1", site="acme"),
        _job("linkedin-99", site="linkedin", title="Site  Reliability Engineer!"),
    ], max_posted_age_days=60, now=NOW)
    assert (stats["inserted"], stats["duplicates"]) == (1, 1)
    assert len(_rows(conn)) == 1


def test_different_city_or_company_is_a_different_job(conn):
    ingest(conn, [_job("a"), _job("b", city="Pune"), _job("c", company="Globex")], max_posted_age_days=60, now=NOW)
    assert len(_rows(conn)) == 3


def test_a_known_source_id_updates_its_row_even_if_the_title_changed(conn):
    ingest(conn, [_job("acme-1", title="SRE")], max_posted_age_days=60, now=NOW)
    ingest(conn, [_job("acme-1", title="Senior SRE")], max_posted_age_days=60, now=NOW + timedelta(hours=6))
    [row] = _rows(conn)
    assert row["title"] == "Senior SRE"


def test_jobs_posted_too_long_ago_are_rejected(conn):
    stats = ingest(conn, [_job(posted="2026-06-01")], max_posted_age_days=60, now=NOW)
    assert (stats["inserted"], stats["rejected_old"]) == (0, 1)
    assert _rows(conn) == []


def test_zero_max_age_means_no_age_limit(conn):
    ingest(conn, [_job(posted="2019-01-01")], max_posted_age_days=0, now=NOW)
    assert len(_rows(conn)) == 1


def test_jobs_without_a_usable_date_are_kept(conn):
    stats = ingest(conn, [_job("a", posted=None), _job("b", posted="whenever", city="Pune")],
                   max_posted_age_days=60, now=NOW)
    assert stats["inserted"] == 2
    assert all(r["posted_at"] is None for r in _rows(conn))


def test_a_stored_job_that_has_aged_out_is_no_longer_touched(conn):
    """So retention (by last_seen) eventually removes it even if the source keeps listing it."""
    ingest(conn, [_job(posted="2026-09-01")], max_posted_age_days=60, now=NOW)
    much_later = NOW + timedelta(days=45)
    stats = ingest(conn, [_job(posted="2026-09-01")], max_posted_age_days=60, now=much_later)
    assert (stats["updated"], stats["rejected_old"]) == (0, 1)
    assert _rows(conn)[0]["last_seen_at"] == NOW.isoformat()


def test_missing_location_and_fields_are_tolerated(conn):
    stats = ingest(conn, [{"id": "x", "title": "Analyst", "site": "s"}], max_posted_age_days=60, now=NOW)
    assert stats["inserted"] == 1
    assert _rows(conn)[0]["location"] is None


def test_jobs_without_a_title_are_skipped(conn):
    stats = ingest(conn, [{"id": "x", "site": "s"}], max_posted_age_days=60, now=NOW)
    assert (stats["inserted"], stats["skipped"]) == (0, 1)


def test_each_run_is_recorded(conn):
    ingest(conn, [_job()], max_posted_age_days=60, now=NOW)
    [run] = [dict(r) for r in conn.execute("SELECT * FROM ingest_runs")]
    assert (run["fetched"], run["inserted"]) == (1, 1)


def test_fingerprint_ignores_case_spacing_and_punctuation():
    assert fingerprint(_job(title="Site Reliability Engineer")) == fingerprint(
        _job(title="  site reliability engineer! ", company="ACME"))
    assert fingerprint(_job()) != fingerprint(_job(city="Pune"))


def test_cli_fetches_once_ingests_and_reports(tmp_path, monkeypatch, capsys):
    import ingest as cli

    monkeypatch.setenv("WAREHOUSE_DB_PATH", str(tmp_path / "wh.db"))
    calls = []

    def fake_fetch():
        calls.append(1)
        return [_job("a"), _job("b", city="Pune"), _job("old", posted="2020-01-01", city="Goa")]

    stats = cli.main(fetch=fake_fetch, now=NOW)
    assert calls == [1]
    assert (stats["inserted"], stats["rejected_old"]) == (2, 1)
    assert '"inserted": 2' in capsys.readouterr().out
    assert not list(tmp_path.glob("*.json*"))  # keep_raw_dumps_days = 0 by default
