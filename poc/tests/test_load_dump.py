import json

from jobhub_poc.loader.load_dump import load_dump


def _write_dump(tmp_path, jobs):
    path = tmp_path / "dump.json"
    path.write_text(json.dumps({"jobs": jobs}))
    return path


def test_insert_new_job_sets_first_seen_equal_last_seen(conn, tmp_path):
    dump = _write_dump(tmp_path, [
        {"id": "abc", "site": "acme", "title": "Data Analyst", "companyName": "Acme",
         "location": {"city": "Remote"}},
    ])
    new_ids = load_dump(conn, dump)
    row = conn.execute("SELECT * FROM jobs WHERE dedupe_key = 'abc'").fetchone()
    assert row["title"] == "Data Analyst"
    assert row["company_name"] == "Acme"
    assert row["first_seen_at"] == row["last_seen_at"]
    assert len(new_ids) == 1
    assert row["id"] in new_ids


def test_reloading_same_job_updates_last_seen_not_first_seen_and_does_not_duplicate(conn, tmp_path):
    dump1 = _write_dump(tmp_path, [
        {"id": "abc", "site": "acme", "title": "Data Analyst", "companyName": "Acme"},
    ])
    load_dump(conn, dump1)
    first_row = conn.execute("SELECT * FROM jobs WHERE dedupe_key = 'abc'").fetchone()

    dump2 = _write_dump(tmp_path, [
        {"id": "abc", "site": "acme", "title": "Senior Data Analyst", "companyName": "Acme"},
    ])
    new_ids = load_dump(conn, dump2)

    rows = conn.execute("SELECT * FROM jobs WHERE dedupe_key = 'abc'").fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == first_row["id"]
    assert row["first_seen_at"] == first_row["first_seen_at"]
    assert row["title"] == "Senior Data Analyst"
    assert new_ids == []  # not a new insert, an update


def test_missing_id_falls_back_to_content_hash_and_still_dedupes(conn, tmp_path):
    job = {"site": "acme", "title": "Product Manager", "companyName": "Acme", "location": {"city": "Pune"}}
    dump1 = _write_dump(tmp_path, [job])
    load_dump(conn, dump1)
    dump2 = _write_dump(tmp_path, [dict(job)])
    load_dump(conn, dump2)
    rows = conn.execute("SELECT * FROM jobs").fetchall()
    assert len(rows) == 1


def test_missing_optional_fields_do_not_raise(conn, tmp_path):
    dump = _write_dump(tmp_path, [
        {"id": "minimal-1", "site": "acme", "title": "Support Engineer", "companyName": "Acme"},
    ])
    load_dump(conn, dump)
    row = conn.execute("SELECT * FROM jobs WHERE dedupe_key = 'minimal-1'").fetchone()
    assert row["location"] is None
    assert row["description"] is None
    assert row["apply_url"] is None


def test_nested_location_object_is_flattened_to_readable_string(conn, tmp_path):
    dump = _write_dump(tmp_path, [
        {"id": "loc-1", "site": "acme", "title": "Engineer", "companyName": "Acme",
         "location": {"city": "San Francisco", "state": "CA", "country": "United States"}},
    ])
    load_dump(conn, dump)
    row = conn.execute("SELECT * FROM jobs WHERE dedupe_key = 'loc-1'").fetchone()
    assert row["location"] == "San Francisco, CA, United States"


def test_partial_location_object_omits_missing_parts(conn, tmp_path):
    dump = _write_dump(tmp_path, [
        {"id": "loc-2", "site": "acme", "title": "Engineer", "companyName": "Acme",
         "location": {"country": "United States"}},
    ])
    load_dump(conn, dump)
    row = conn.execute("SELECT * FROM jobs WHERE dedupe_key = 'loc-2'").fetchone()
    assert row["location"] == "United States"


def test_apply_url_falls_back_from_apply_url_to_job_url(conn, tmp_path):
    dump = _write_dump(tmp_path, [
        {"id": "url-1", "site": "acme", "title": "Engineer", "companyName": "Acme",
         "jobUrl": "https://example.com/apply"},
    ])
    load_dump(conn, dump)
    row = conn.execute("SELECT * FROM jobs WHERE dedupe_key = 'url-1'").fetchone()
    assert row["apply_url"] == "https://example.com/apply"


def test_raw_json_round_trips_exactly(conn, tmp_path):
    job = {"id": "raw-1", "site": "acme", "title": "Engineer", "companyName": "Acme",
           "compensation": {"currency": "USD", "minAmount": 100000}}
    dump = _write_dump(tmp_path, [job])
    load_dump(conn, dump)
    row = conn.execute("SELECT raw_json FROM jobs WHERE dedupe_key = 'raw-1'").fetchone()
    assert json.loads(row["raw_json"]) == job


def test_load_real_captured_fixture_end_to_end(conn):
    import pathlib
    fixture = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "sample_everjobs_response_real.json"
    new_ids = load_dump(conn, fixture)
    assert len(new_ids) == 4
    rows = conn.execute("SELECT title, location FROM jobs ORDER BY title").fetchall()
    titles = [r["title"] for r in rows]
    assert "Senior Platform Engineer" in titles
    # the Abridge job's location has only a country, no city/state
    abridge = conn.execute("SELECT location FROM jobs WHERE dedupe_key LIKE 'abridge-%'").fetchone()
    assert abridge["location"] == "United States"
