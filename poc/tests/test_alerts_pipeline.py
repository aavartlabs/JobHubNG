import json

import pytest

from jobhub_poc import config
from jobhub_poc.alerts.contacts import Contact
from jobhub_poc.alerts.delivery import deliver
from jobhub_poc.alerts.matcher import find_matches

ORIGIN = "https://jobhubs.example"


def _job(conn, key, title, location="Bengaluru, KA, in", company="Acme", description="", is_remote=0):
    return conn.execute(
        "INSERT INTO jobs (dedupe_key, source_site, title, company_name, location, description, is_remote, "
        "first_seen_at, last_seen_at, raw_json) VALUES (?, 's', ?, ?, ?, ?, ?, 'x', 'x', '{}')",
        (key, title, company, location, description, is_remote)).lastrowid


def _sub(conn, owner="u1", titles=(), locations=(), companies=(), keywords=(), work_mode=None,
         email=0, whatsapp=1, active=1):
    sid = conn.execute(
        "INSERT INTO alert_subscriptions (owner_auth_user_id, titles, locations, companies, keywords, work_mode, "
        "notify_email, notify_whatsapp, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 't')",
        (owner, json.dumps(list(titles)), json.dumps(list(locations)), json.dumps(list(companies)),
         json.dumps(list(keywords)), work_mode, email, whatsapp, active)).lastrowid
    conn.commit()
    return sid


VERIFIED = Contact(email="a@x.com", email_verified=True, phone="+15550000001", phone_verified=True)


class RecordingSender:
    def __init__(self, fail=()):
        self.sent, self.fail = [], set(fail)

    def whatsapp(self, phone, text):
        if "whatsapp" in self.fail:
            raise RuntimeError("gateway down")
        self.sent.append(("whatsapp", phone, text))

    def email(self, to, subject, text, html):
        if "email" in self.fail:
            raise RuntimeError("resend down")
        self.sent.append(("email", to, subject))


def _rows(conn):
    return [dict(r) for r in conn.execute("SELECT subscription_id, job_id, channel, status FROM alerts_sent ORDER BY id")]


# ---- matching ----

def test_matches_are_grouped_per_alert_and_only_consider_new_jobs(conn):
    a = _job(conn, "a", "Senior SRE")
    b = _job(conn, "b", "DevOps Engineer", location="Remote", is_remote=1)
    old = _job(conn, "old", "SRE II")
    _job(conn, "c", "Chef")
    sub = _sub(conn, titles=("sre", "devops"))
    [m] = find_matches(conn, [a, b, 4])
    assert m.subscription_id == sub
    assert sorted(j["id"] for j in m.jobs) == [a, b]
    assert old not in [j["id"] for j in m.jobs]


def test_inactive_alerts_and_alerts_with_no_matches_are_left_out(conn):
    a = _job(conn, "a", "Senior SRE")
    _sub(conn, titles=("sre",), active=0)
    _sub(conn, titles=("golang",))
    assert find_matches(conn, [a]) == []


# ---- delivery ----

def test_one_digest_per_alert_per_channel(conn):
    ids = [_job(conn, f"k{i}", f"SRE {i}") for i in range(3)]
    sub = _sub(conn, titles=("sre",), email=1, whatsapp=1)
    sender = RecordingSender()
    stats = deliver(conn, find_matches(conn, ids), {"u1": VERIFIED}, sender, "live", ORIGIN)
    assert [s[0] for s in sender.sent] == ["email", "whatsapp"]
    assert "3 new jobs" in sender.sent[1][2]
    assert stats == {"digests_sent": 2, "digests_failed": 0, "skipped": 0, "deactivated": 0}
    assert len(_rows(conn)) == 6 and {r["status"] for r in _rows(conn)} == {"SENT"}


def test_rerunning_never_resends(conn):
    a = _job(conn, "a", "SRE")
    _sub(conn, titles=("sre",))
    sender = RecordingSender()
    deliver(conn, find_matches(conn, [a]), {"u1": VERIFIED}, sender, "live", ORIGIN)
    deliver(conn, find_matches(conn, [a]), {"u1": VERIFIED}, sender, "live", ORIGIN)
    assert len(sender.sent) == 1


def test_unverified_channel_is_skipped_and_recorded(conn):
    a = _job(conn, "a", "SRE")
    _sub(conn, titles=("sre",), email=1, whatsapp=1)
    half = Contact(email="a@x.com", email_verified=True, phone="+15550000001", phone_verified=False)
    sender = RecordingSender()
    stats = deliver(conn, find_matches(conn, [a]), {"u1": half}, sender, "live", ORIGIN)
    assert [s[0] for s in sender.sent] == ["email"]
    assert {(r["channel"], r["status"]) for r in _rows(conn)} == {("email", "SENT"), ("whatsapp", "SKIPPED")}
    assert stats["skipped"] == 1


def test_a_failed_send_is_recorded_as_failed(conn):
    a = _job(conn, "a", "SRE")
    _sub(conn, titles=("sre",))
    stats = deliver(conn, find_matches(conn, [a]), {"u1": VERIFIED}, RecordingSender(fail={"whatsapp"}), "live", ORIGIN)
    assert [r["status"] for r in _rows(conn)] == ["FAILED"]
    assert stats["digests_failed"] == 1


def test_alerts_of_deleted_users_are_deactivated_without_sending(conn):
    a = _job(conn, "a", "SRE")
    sub = _sub(conn, owner="gone", titles=("sre",))
    sender = RecordingSender()
    stats = deliver(conn, find_matches(conn, [a]), {"u1": VERIFIED}, sender, "live", ORIGIN)
    assert sender.sent == [] and _rows(conn) == []
    assert conn.execute("SELECT is_active FROM alert_subscriptions WHERE id = ?", (sub,)).fetchone()[0] == 0
    assert stats["deactivated"] == 1


def test_run_alerts_does_nothing_without_matches_and_never_calls_auth(conn, requests_mock):
    from jobhub_poc.alerts import run_alerts

    assert run_alerts.run(conn, [], backend="console") == {"matched_alerts": 0}
    assert requests_mock.call_count == 0


def test_run_alerts_aborts_before_writing_if_contacts_unavailable(conn, monkeypatch):
    from jobhub_poc.alerts import run_alerts
    from jobhub_poc.auth_admin_client import AuthServiceError

    a = _job(conn, "a", "SRE")
    _sub(conn, titles=("sre",))

    def boom():
        raise AuthServiceError("auth-service unreachable")

    monkeypatch.setattr(run_alerts, "load_contacts", boom)
    with pytest.raises(AuthServiceError):
        run_alerts.run(conn, [a], backend="console")
    assert _rows(conn) == []
