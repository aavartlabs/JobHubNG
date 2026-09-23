import gzip
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cold_export import export_cold
from warehouse import ingest, open_warehouse, purge_warehouse

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _job(job_id, desc="v1", city="Bengaluru"):
    return {"id": job_id, "title": "SRE", "companyName": "Acme", "site": "s",
            "location": {"city": city}, "datePosted": None, "description": desc}


class FakeUploader:
    def __init__(self, fail=False, corrupt=False):
        self.objects, self.fail, self.corrupt = {}, fail, corrupt

    def upload(self, path, key, sha256):
        if self.fail:
            raise RuntimeError("minio down")
        data = path.read_bytes()
        self.objects[key] = b"x" if self.corrupt else data
        return len(self.objects[key])


def _lines(blob):
    return [json.loads(line) for line in gzip.decompress(blob).decode().splitlines()]


@pytest.fixture
def conn(tmp_path):
    """a: live, with two old versions (v1 until day 1, v2 until day 2); b: archived on day 40."""
    c = open_warehouse(tmp_path / "wh.db")
    ingest(c, [_job("a", "v1"), _job("b", city="Pune")], 0, now=T0)
    ingest(c, [_job("a", "v2")], 0, now=T0 + timedelta(days=1))
    ingest(c, [_job("a", "v3")], 0, now=T0 + timedelta(days=2))
    ingest(c, [_job("a", "v3")], 0, now=T0 + timedelta(days=39))  # still listed, unchanged
    purge_warehouse(c, 30, now=T0 + timedelta(days=40))            # b retires to jobs_archive
    yield c
    c.close()


NOW = T0 + timedelta(days=200)


def test_old_archive_rows_and_versions_are_exported_then_removed(conn, tmp_path):
    up = FakeUploader()
    stats = export_cold(conn, cold_after_days=90, uploader=up, workdir=tmp_path, now=NOW)
    assert stats == {"archived_jobs": 1, "versions": 2}
    archive_key = next(k for k in up.objects if k.endswith("jobs_archive.jsonl.gz"))
    versions_key = next(k for k in up.objects if k.endswith("job_versions.jsonl.gz"))
    assert archive_key.startswith("archive/history/2026-07-20/")
    [archived] = _lines(up.objects[archive_key])
    assert archived["source_id"] == "b" and json.loads(archived["raw_json"])["id"] == "b"
    descs = sorted(v["raw_json"]["description"] for v in _lines(up.objects[versions_key]))
    assert descs == ["v1", "v2"]  # decompressed: readable without zlib
    assert conn.execute("SELECT count(*) FROM jobs_archive").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM job_versions").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1  # live job untouched


def test_recent_history_stays(conn, tmp_path):
    up = FakeUploader()
    stats = export_cold(conn, cold_after_days=365, uploader=up, workdir=tmp_path, now=NOW)
    assert stats == {"archived_jobs": 0, "versions": 0}
    assert up.objects == {}
    assert conn.execute("SELECT count(*) FROM job_versions").fetchone()[0] == 2


@pytest.mark.parametrize("uploader", [FakeUploader(fail=True), FakeUploader(corrupt=True)])
def test_nothing_is_deleted_unless_the_upload_is_verified(conn, tmp_path, uploader):
    with pytest.raises(RuntimeError):
        export_cold(conn, cold_after_days=90, uploader=uploader, workdir=tmp_path, now=NOW)
    assert conn.execute("SELECT count(*) FROM jobs_archive").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM job_versions").fetchone()[0] == 2
