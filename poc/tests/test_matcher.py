from jobhub_poc.alerts.matcher import find_matches


def _insert_job(conn, title, location="Remote"):
    cur = conn.execute(
        """
        INSERT INTO jobs (dedupe_key, source_site, title, location, first_seen_at, last_seen_at, raw_json)
        VALUES (?, 'acme', ?, ?, '2026-09-16T00:00:00+00:00', '2026-09-16T00:00:00+00:00', '{}')
        """,
        (title, title, location),
    )
    conn.commit()
    return cur.lastrowid


def _insert_subscription(conn, phone, title_keyword=None, location_keyword=None, is_active=1):
    cur = conn.execute(
        """
        INSERT INTO alert_subscriptions (phone_number, title_keyword, location_keyword, is_active, created_at)
        VALUES (?, ?, ?, ?, '2026-09-16T00:00:00+00:00')
        """,
        (phone, title_keyword, location_keyword, is_active),
    )
    conn.commit()
    return cur.lastrowid


def test_title_keyword_matches_case_insensitively(conn):
    job_id = _insert_job(conn, "Senior ENGINEER")
    sub_id = _insert_subscription(conn, "+1000", title_keyword="engineer")
    matches = find_matches(conn, [job_id])
    assert [(m.subscription_id, m.job_id) for m in matches] == [(sub_id, job_id)]


def test_location_keyword_matches(conn):
    job_id = _insert_job(conn, "Analyst", location="Bengaluru, India")
    sub_id = _insert_subscription(conn, "+1000", location_keyword="bengaluru")
    matches = find_matches(conn, [job_id])
    assert [(m.subscription_id, m.job_id) for m in matches] == [(sub_id, job_id)]


def test_empty_criteria_matches_any_new_job(conn):
    job_id = _insert_job(conn, "Whatever Title")
    sub_id = _insert_subscription(conn, "+1000")
    matches = find_matches(conn, [job_id])
    assert [(m.subscription_id, m.job_id) for m in matches] == [(sub_id, job_id)]


def test_only_new_job_ids_are_considered(conn):
    stale_job_id = _insert_job(conn, "Engineer")
    _insert_subscription(conn, "+1000", title_keyword="engineer")
    matches = find_matches(conn, [])  # stale job not passed as "new"
    assert matches == []


def test_inactive_subscriptions_are_skipped(conn):
    job_id = _insert_job(conn, "Engineer")
    _insert_subscription(conn, "+1000", title_keyword="engineer", is_active=0)
    matches = find_matches(conn, [job_id])
    assert matches == []


def test_non_matching_title_keyword_excluded(conn):
    job_id = _insert_job(conn, "Product Manager")
    _insert_subscription(conn, "+1000", title_keyword="engineer")
    matches = find_matches(conn, [job_id])
    assert matches == []
