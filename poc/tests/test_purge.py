from datetime import datetime, timedelta, timezone

from jobhub_poc.loader.purge import purge


def _insert_job(conn, dedupe_key, first_seen_at):
    conn.execute(
        """
        INSERT INTO jobs (dedupe_key, source_site, title, first_seen_at, last_seen_at, raw_json)
        VALUES (?, 'acme', 'Some Title', ?, ?, '{}')
        """,
        (dedupe_key, first_seen_at, first_seen_at),
    )
    conn.commit()


def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


def test_purge_deletes_rows_older_than_window_keeps_newer(conn):
    _insert_job(conn, "old", _days_ago(16))
    _insert_job(conn, "new", _days_ago(1))
    deleted = purge(conn, window_days=15)
    assert deleted == 1
    remaining = [r["dedupe_key"] for r in conn.execute("SELECT dedupe_key FROM jobs")]
    assert remaining == ["new"]


def test_purge_boundary_exactly_at_window_is_kept(conn):
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=15)).isoformat()
    _insert_job(conn, "boundary", cutoff)
    deleted = purge(conn, window_days=15, now=now)
    assert deleted == 0
    remaining = [r["dedupe_key"] for r in conn.execute("SELECT dedupe_key FROM jobs")]
    assert remaining == ["boundary"]


def test_purge_just_past_boundary_is_deleted(conn):
    now = datetime.now(timezone.utc)
    just_past = (now - timedelta(days=15, seconds=1)).isoformat()
    _insert_job(conn, "just-past", just_past)
    deleted = purge(conn, window_days=15, now=now)
    assert deleted == 1


def test_purge_on_clean_table_is_noop(conn):
    _insert_job(conn, "fresh", _days_ago(0))
    deleted = purge(conn, window_days=15)
    assert deleted == 0
