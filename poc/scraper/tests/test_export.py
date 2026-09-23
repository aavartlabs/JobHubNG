import gzip
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from export import export_delta
from warehouse import ingest, open_warehouse

T0 = datetime(2026, 9, 23, 0, 0, tzinfo=timezone.utc)


def _job(job_id, title, city="Bengaluru", **extra):
    return {"id": job_id, "title": title, "companyName": "Acme", "site": "acme",
            "location": {"city": city, "country": "in"}, "datePosted": "2026-09-20",
            "jobUrl": f"https://x/{job_id}", **extra}


@pytest.fixture
def conn(tmp_path):
    c = open_warehouse(tmp_path / "wh.db")
    yield c
    c.close()


def _read(path):
    with gzip.open(path, "rt") as f:
        return [json.loads(line) for line in f]


def test_exports_only_jobs_matching_a_serving_term(conn, tmp_path):
    ingest(conn, [_job("a", "Senior SRE"), _job("b", "DevOps Engineer"), _job("c", "Chef")], 60, now=T0)
    out = tmp_path / "d.jsonl.gz"
    result = export_delta(conn, since=None, terms=("sre", "devops"), locations=(), out_path=out)
    records = _read(out)
    assert sorted(r["dedupe_key"] for r in records) == ["a", "b"]
    assert result == {"exported": 2, "touched": 0, "watermark": T0.isoformat()}


def test_record_shape_carries_seen_times_matched_term_and_the_raw_job(conn, tmp_path):
    ingest(conn, [_job("a", "Senior SRE")], 60, now=T0)
    export_delta(conn, None, ("sre",), (), tmp_path / "d.jsonl.gz")
    [rec] = _read(tmp_path / "d.jsonl.gz")
    assert rec["first_seen_at"] == rec["last_seen_at"] == T0.isoformat()
    assert rec["search_term"] == "sre"
    assert rec["job"]["id"] == "a" and rec["job"]["title"] == "Senior SRE"


def test_after_the_watermark_changed_rows_go_in_full_and_merely_seen_rows_as_touches(conn, tmp_path):
    ingest(conn, [_job("a", "SRE"), _job("b", "SRE II", city="Pune"), _job("c", "SRE III", city="Goa")], 60, now=T0)
    later = T0 + timedelta(hours=6)
    ingest(conn, [_job("b", "SRE II", city="Pune"),                        # seen, unchanged
                  _job("c", "SRE III", city="Goa", description="new")],    # seen, changed
           60, now=later)                                                  # a: not seen
    result = export_delta(conn, since=T0.isoformat(), terms=("sre",), locations=(), out_path=tmp_path / "d.gz")
    records = {r["dedupe_key"]: r for r in _read(tmp_path / "d.gz")}
    assert sorted(records) == ["b", "c"]
    assert records["b"] == {"dedupe_key": "b", "last_seen_at": later.isoformat(), "touch": True}
    assert records["c"]["job"]["description"] == "new"
    assert result == {"exported": 1, "touched": 1, "watermark": later.isoformat()}


def test_nothing_new_keeps_the_watermark(conn, tmp_path):
    ingest(conn, [_job("a", "SRE")], 60, now=T0)
    result = export_delta(conn, since=T0.isoformat(), terms=("sre",), locations=(), out_path=tmp_path / "d.gz")
    assert result == {"exported": 0, "touched": 0, "watermark": T0.isoformat()}
    assert _read(tmp_path / "d.gz") == []


def test_location_filter_applies_when_set(conn, tmp_path):
    ingest(conn, [_job("a", "SRE"), _job("b", "SRE", city="Berlin", companyName="Other")], 60, now=T0)
    export_delta(conn, None, ("sre",), ("bengaluru",), tmp_path / "d.gz")
    assert [r["dedupe_key"] for r in _read(tmp_path / "d.gz")] == ["a"]


def test_rows_without_an_everjobs_id_get_a_stable_warehouse_key(conn, tmp_path):
    ingest(conn, [{"title": "SRE", "companyName": "Acme", "site": "s"}], 60, now=T0)
    export_delta(conn, None, ("sre",), (), tmp_path / "d.gz")
    [rec] = _read(tmp_path / "d.gz")
    assert rec["dedupe_key"].startswith("wh-")


def test_extra_alert_terms_also_export_matches_in_title_or_description(conn, tmp_path):
    ingest(conn, [_job("a", "CloudOps Engineer"), _job("b", "Platform Lead", description="We run Terraform"),
                  _job("c", "Chef")], 60, now=T0)
    result = export_delta(conn, None, ("sre",), (), tmp_path / "d.gz", extra_terms=("cloudops", "terraform"))
    assert sorted(r["dedupe_key"] for r in _read(tmp_path / "d.gz")) == ["a", "b"]
    assert result["exported"] == 2


def test_cli_reads_extra_terms_file(conn, tmp_path, monkeypatch):
    import json as _json
    import export as cli

    ingest(conn, [_job("a", "CloudOps Engineer")], 60, now=T0)
    conn.close()
    monkeypatch.setenv("WAREHOUSE_DB_PATH", str(tmp_path / "wh.db"))
    terms = tmp_path / "terms.json"
    terms.write_text(_json.dumps(["cloudops"]))
    result = cli.main(["--out", str(tmp_path / "d.gz"), "--extra-terms-file", str(terms)])
    assert result["exported"] == 1
