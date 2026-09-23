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


def _insert_job_seen(conn, dedupe_key, first_seen_at, last_seen_at):
    cur = conn.execute(
        """
        INSERT INTO jobs (dedupe_key, source_site, title, first_seen_at, last_seen_at, raw_json)
        VALUES (?, 'acme', 'Some Title', ?, ?, '{}')
        """,
        (dedupe_key, first_seen_at, last_seen_at),
    )
    conn.commit()
    return cur.lastrowid


def test_purge_is_keyed_on_last_seen_so_still_listed_jobs_survive(conn):
    """A job first seen 40 days ago but still in every sweep is live, not stale."""
    _insert_job_seen(conn, "long-running", _days_ago(40), _days_ago(0))
    _insert_job_seen(conn, "gone", _days_ago(40), _days_ago(16))
    assert purge(conn, window_days=15) == 1
    assert [r["dedupe_key"] for r in conn.execute("SELECT dedupe_key FROM jobs")] == ["long-running"]


def test_purging_a_job_that_was_alerted_on_does_not_fail(conn):
    """alerts_sent.job_id references jobs(id) with foreign keys ON: the purge must clear
    those rows first, or the first aged-out alerted job crashes the pipeline."""
    job_id = _insert_job_seen(conn, "alerted", _days_ago(30), _days_ago(20))
    sub = conn.execute(
        "INSERT INTO alert_subscriptions (phone_number, owner_auth_user_id, is_active, created_at) "
        "VALUES ('+15550000001', 'u1', 1, 'x')"
    ).lastrowid
    conn.execute(
        "INSERT INTO alerts_sent (subscription_id, job_id, notifier_backend, message, sent_at, status) "
        "VALUES (?, ?, 'console', 'm', 'x', 'SENT')", (sub, job_id))
    conn.commit()
    assert purge(conn, window_days=15) == 1
    assert conn.execute("SELECT count(*) FROM alerts_sent").fetchone()[0] == 0


def test_default_window_comes_from_pipeline_ini(conn, monkeypatch, tmp_path):
    from jobhub_poc.loader import purge as purge_module

    ini = tmp_path / "p.ini"
    ini.write_text("[retention]\nserving_retention_days = 3\n")
    monkeypatch.setenv("JOBHUB_PIPELINE_INI", str(ini))
    assert purge_module.default_window_days() == 3
