import json

from jobhub_poc.alerts.alert_terms import active_alert_terms, terms_fingerprint


def _sub(conn, titles=(), keywords=(), active=1):
    conn.execute("INSERT INTO alert_subscriptions (owner_auth_user_id, titles, keywords, notify_email, is_active, created_at) "
                 "VALUES ('u', ?, ?, 1, ?, 't')", (json.dumps(list(titles)), json.dumps(list(keywords)), active))
    conn.commit()


def test_active_alert_titles_and_keywords_deduped_and_sorted(conn):
    _sub(conn, titles=("sre", "cloudops"), keywords=("terraform",))
    _sub(conn, titles=("sre",))
    _sub(conn, titles=("paused only",), active=0)
    assert active_alert_terms(conn, cap=200) == ["cloudops", "sre", "terraform"]


def test_cap_limits_the_term_count(conn):
    _sub(conn, titles=tuple(f"t{i:02d}" for i in range(10)))
    assert len(active_alert_terms(conn, cap=3)) == 3


def test_fingerprint_changes_only_when_the_set_changes():
    assert terms_fingerprint(["a", "b"]) == terms_fingerprint(["a", "b"])
    assert terms_fingerprint(["a", "b"]) != terms_fingerprint(["a", "c"])
