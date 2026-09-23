from jobhub_poc.alerts.digest import MAX_LISTED, build_email, build_whatsapp, describe_rule
from jobhub_poc.alerts.rules import Rule

ORIGIN = "https://jobhubs.example"


def _jobs(n):
    return [{"id": i, "title": f"SRE {i}", "company_name": "Acme", "location": "Bengaluru"} for i in range(1, n + 1)]


def test_describe_rule_is_short_and_readable():
    rule = Rule(titles=("sre", "devops"), locations=("bangalore",), work_mode="remote", companies=("acme",))
    assert describe_rule(rule) == "sre, devops · bangalore · at acme · remote"


def test_whatsapp_digest_lists_jobs_with_links_back_to_jobhub():
    text = build_whatsapp(Rule(titles=("sre",)), _jobs(2), ORIGIN)
    assert text.startswith('*JobHub: 2 new jobs for "sre"*')
    assert "1. SRE 1 — Acme — Bengaluru\n   https://jobhubs.example/jobs?job=1" in text
    assert text.rstrip().endswith("Manage alerts: https://jobhubs.example/alerts")


def test_digest_caps_the_list_and_says_how_many_more():
    text = build_whatsapp(Rule(titles=("sre",)), _jobs(MAX_LISTED + 3), ORIGIN)
    assert f"{MAX_LISTED}. SRE {MAX_LISTED}" in text
    assert f"SRE {MAX_LISTED + 1}" not in text
    assert "…and 3 more on JobHub: https://jobhubs.example/jobs" in text


def test_singular_wording_for_one_job():
    assert build_whatsapp(Rule(titles=("sre",)), _jobs(1), ORIGIN).startswith('*JobHub: 1 new job for "sre"*')


def test_email_has_subject_text_and_escaped_html():
    jobs = [{"id": 7, "title": "SRE <script>", "company_name": "A&B", "location": None}]
    subject, text, html = build_email(Rule(titles=("sre",)), jobs, ORIGIN)
    assert subject == 'JobHub: 1 new job for "sre"'
    assert "SRE <script> — A&B" in text
    assert "&lt;script&gt;" in html and "A&amp;B" in html and "<script>" not in html
    assert 'href="https://jobhubs.example/jobs?job=7"' in html
    assert "https://jobhubs.example/alerts" in html
