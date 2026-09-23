import gzip
import json

from jobhub_poc.loader.load_delta import get_watermark, load_delta
from jobhub_poc.loader.load_dump import load_dump


def _write(tmp_path, records, name="d.jsonl.gz"):
    path = tmp_path / name
    with gzip.open(path, "wt") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return path


def _rec(key, title="SRE", first="2026-09-20T00:00:00+00:00", last="2026-09-23T00:00:00+00:00", **job):
    return {"dedupe_key": key, "first_seen_at": first, "last_seen_at": last, "search_term": "sre",
            "job": {"id": key, "title": title, "companyName": "Acme", "site": "acme",
                    "location": {"city": "Bengaluru", "country": "in"}, "jobUrl": f"https://x/{key}", **job}}


def _jobs(conn):
    return {r["dedupe_key"]: dict(r) for r in conn.execute("SELECT * FROM jobs")}


def test_new_records_are_inserted_with_warehouse_seen_times_and_reported_as_new(conn, tmp_path):
    new_ids = load_delta(conn, _write(tmp_path, [_rec("a"), _rec("b", title="DevOps")]),
                         watermark="2026-09-23T00:00:00+00:00")
    rows = _jobs(conn)
    assert sorted(rows) == ["a", "b"]
    assert sorted(new_ids) == sorted(r["id"] for r in rows.values())
    assert rows["a"]["first_seen_at"] == "2026-09-20T00:00:00+00:00"
    assert rows["a"]["last_seen_at"] == "2026-09-23T00:00:00+00:00"
    assert rows["a"]["location"] == "Bengaluru, in"
    assert rows["a"]["search_term"] == "sre"


def test_existing_rows_are_updated_not_reported_as_new(conn, tmp_path):
    load_delta(conn, _write(tmp_path, [_rec("a")]), watermark="w1")
    new_ids = load_delta(conn, _write(tmp_path, [_rec("a", title="Senior SRE", last="2026-09-24T00:00:00+00:00")],
                                      name="e.gz"), watermark="w2")
    assert new_ids == []
    row = _jobs(conn)["a"]
    assert row["title"] == "Senior SRE"
    assert row["last_seen_at"] == "2026-09-24T00:00:00+00:00"
    assert row["first_seen_at"] == "2026-09-20T00:00:00+00:00"  # never moved by an update


def test_jobs_loaded_by_the_old_dump_path_are_recognised_by_their_everjobs_id(conn, tmp_path):
    """Cutover continuity: rows already on pi09 must not come back as 'new' (re-alerting)."""
    dump = tmp_path / "dump.json"
    dump.write_text(json.dumps({"jobs": [{"id": "a", "title": "SRE", "site": "acme"}]}))
    load_dump(conn, dump)
    assert load_delta(conn, _write(tmp_path, [_rec("a")]), watermark="w") == []
    assert len(_jobs(conn)) == 1


def test_watermark_is_stored_and_only_advanced_on_success(conn, tmp_path):
    assert get_watermark(conn) is None
    load_delta(conn, _write(tmp_path, [_rec("a")]), watermark="2026-09-23T00:00:00+00:00")
    assert get_watermark(conn) == "2026-09-23T00:00:00+00:00"

    bad = tmp_path / "bad.gz"
    with gzip.open(bad, "wt") as f:
        f.write(json.dumps(_rec("b")) + "\n{not json\n")
    try:
        load_delta(conn, bad, watermark="2026-09-24T00:00:00+00:00")
    except ValueError:
        pass
    assert get_watermark(conn) == "2026-09-23T00:00:00+00:00"
    assert "b" not in _jobs(conn)  # the whole delta is one transaction


def test_an_empty_delta_still_records_the_watermark(conn, tmp_path):
    assert load_delta(conn, _write(tmp_path, []), watermark="2026-09-25T00:00:00+00:00") == []
    assert get_watermark(conn) == "2026-09-25T00:00:00+00:00"


def test_touch_records_only_refresh_last_seen(conn, tmp_path):
    load_delta(conn, _write(tmp_path, [_rec("a")]), watermark="w1")
    new_ids = load_delta(conn, _write(tmp_path, [
        {"dedupe_key": "a", "last_seen_at": "2026-09-30T00:00:00+00:00", "touch": True},
        {"dedupe_key": "never-seen-here", "last_seen_at": "2026-09-30T00:00:00+00:00", "touch": True},
    ], name="t.gz"), watermark="w2")
    assert new_ids == []
    rows = _jobs(conn)
    assert sorted(rows) == ["a"]  # a touch can't create a row: it carries no job content
    assert rows["a"]["last_seen_at"] == "2026-09-30T00:00:00+00:00"
    assert rows["a"]["title"] == "SRE"
