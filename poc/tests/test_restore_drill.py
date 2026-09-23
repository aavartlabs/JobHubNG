import gzip
import hashlib
import json
import sqlite3
from datetime import date

import pytest

from jobhub_poc.ops import restore_drill
from jobhub_poc.ops.restore_drill import Target, drill


def _gz_db(tmp_path, name, table, rows):
    import uuid
    path = tmp_path / f"src-{uuid.uuid4().hex}-{name}"
    conn = sqlite3.connect(path)
    conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)")
    conn.executemany(f"INSERT INTO {table} DEFAULT VALUES", [()] * rows)
    conn.commit()
    conn.close()
    return gzip.compress(path.read_bytes())


class FakeStore:
    """Stands in for `mc` against jobshub-data: {key: (bytes, sha256-metadata)}."""

    def __init__(self):
        self.objects = {}

    def put(self, key, data, sha=None):
        self.objects[key] = (data, sha if sha is not None else hashlib.sha256(data).hexdigest())

    def list_dates(self, prefix):
        return sorted({k[len(prefix):].split("/")[0] for k in self.objects if k.startswith(prefix)})

    def stat(self, key):
        if key not in self.objects:
            return None
        data, sha = self.objects[key]
        return {"size": len(data), "sha256": sha}

    def download(self, key, dest):
        dest.write_bytes(self.objects[key][0])


TARGETS = [Target("pi09", "jobhub.db", ("jobs",)), Target("pi05", "warehouse.db", ("jobs",))]
TODAY = date(2026, 9, 27)


def _healthy(tmp_path, store, day="2026-09-26"):
    for host, name in (("pi09", "jobhub.db"), ("pi05", "warehouse.db")):
        store.put(f"backups/daily/{day}/{host}/{name}.gz", _gz_db(tmp_path, name, "jobs", 5))


def test_all_good(tmp_path):
    store = FakeStore()
    _healthy(tmp_path, store)
    results = drill(store, TARGETS, today=TODAY, max_age_days=2, workdir=tmp_path)
    assert [r.ok for r in results] == [True, True]
    assert results[0].date == "2026-09-26" and results[0].counts == {"jobs": 5}


def test_uses_the_newest_backup_that_has_this_database(tmp_path):
    store = FakeStore()
    _healthy(tmp_path, store, day="2026-09-25")
    store.put("backups/daily/2026-09-26/pi09/jobhub.db.gz", _gz_db(tmp_path, "jobhub.db", "jobs", 9))
    results = drill(store, TARGETS, today=TODAY, max_age_days=2, workdir=tmp_path)
    assert (results[0].date, results[0].counts) == ("2026-09-26", {"jobs": 9})
    assert results[1].date == "2026-09-25"  # pi05's newest is older, still found


def test_stale_backup_fails(tmp_path):
    store = FakeStore()
    _healthy(tmp_path, store, day="2026-09-20")
    results = drill(store, TARGETS, today=TODAY, max_age_days=2, workdir=tmp_path)
    assert not results[0].ok and "7 days old" in results[0].problem


def test_missing_backup_fails(tmp_path):
    results = drill(FakeStore(), TARGETS, today=TODAY, max_age_days=2, workdir=tmp_path)
    assert not any(r.ok for r in results) and "no backup" in results[0].problem


def test_checksum_mismatch_fails(tmp_path):
    store = FakeStore()
    _healthy(tmp_path, store)
    data, _ = store.objects["backups/daily/2026-09-26/pi09/jobhub.db.gz"]
    store.put("backups/daily/2026-09-26/pi09/jobhub.db.gz", data, sha="0" * 64)
    results = drill(store, TARGETS, today=TODAY, max_age_days=2, workdir=tmp_path)
    assert not results[0].ok and "sha256" in results[0].problem


def test_corrupt_or_empty_database_fails(tmp_path):
    store = FakeStore()
    _healthy(tmp_path, store)
    store.put("backups/daily/2026-09-26/pi09/jobhub.db.gz", gzip.compress(b"not a database"))
    store.put("backups/daily/2026-09-26/pi05/warehouse.db.gz", _gz_db(tmp_path, "w", "jobs", 0))
    results = drill(store, TARGETS, today=TODAY, max_age_days=2, workdir=tmp_path)
    assert not results[0].ok
    assert not results[1].ok and "jobs is empty" in results[1].problem


def test_downloads_are_cleaned_up(tmp_path):
    store = FakeStore()
    _healthy(tmp_path, store)
    work = tmp_path / "work"
    work.mkdir()
    drill(store, TARGETS, today=TODAY, max_age_days=2, workdir=work)
    assert list(work.iterdir()) == []
