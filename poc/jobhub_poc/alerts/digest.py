"""One digest message per alert per channel per pipeline run. Pure; no I/O.

Links go to the job on JobsHub (/jobs?job=<id>), not straight to the employer: details
and Apply are behind sign-in there, and each view/apply is recorded as signal for the
future tracker and recommendations. At most MAX_LISTED jobs are listed; the rest are
summarised, so a big run is still one short message rather than a burst.
"""
from html import escape

MAX_LISTED = 10


def describe_rule(rule):
    parts = []
    if rule.titles:
        parts.append(", ".join(rule.titles))
    if rule.locations:
        parts.append(", ".join(rule.locations))
    if rule.companies:
        parts.append("at " + ", ".join(rule.companies))
    if rule.keywords:
        parts.append("mentioning " + ", ".join(rule.keywords))
    if rule.work_mode:
        parts.append({"remote": "remote", "onsite": "on-site"}[rule.work_mode])
    return " · ".join(parts)


def _headline(rule, count):
    return f'JobsHub: {count} new job{"" if count == 1 else "s"} for "{describe_rule(rule)}"'


def _line(job):
    return " — ".join(p for p in (job.get("title"), job.get("company_name"), job.get("location")) if p)


def _job_url(origin, job):
    return f"{origin}/jobs?job={job['id']}"


def build_telegram(rule, jobs, origin):
    """Plain text: the gateway sends without a parse mode, so nothing needs escaping."""
    lines = [_headline(rule, len(jobs)), ""]
    for i, job in enumerate(jobs[:MAX_LISTED], 1):
        lines.append(f"{i}. {_line(job)}\n   {_job_url(origin, job)}")
    if len(jobs) > MAX_LISTED:
        lines.append(f"\n…and {len(jobs) - MAX_LISTED} more on JobsHub: {origin}/jobs")
    lines.append(f"\nManage alerts: {origin}/alerts")
    return "\n".join(lines)


def build_email(rule, jobs, origin):
    """(subject, text, html)."""
    subject = _headline(rule, len(jobs))
    listed = jobs[:MAX_LISTED]
    more = len(jobs) - len(listed)

    text_lines = [subject, ""]
    text_lines += [f"{i}. {_line(job)}\n   {_job_url(origin, job)}" for i, job in enumerate(listed, 1)]
    if more:
        text_lines.append(f"\n…and {more} more on JobsHub: {origin}/jobs")
    text_lines.append(f"\nManage or stop these alerts: {origin}/alerts")

    items = "".join(
        f'<li><a href="{escape(_job_url(origin, job))}">{escape(job.get("title") or "")}</a>'
        f'{escape(" — " + job["company_name"]) if job.get("company_name") else ""}'
        f'{escape(" — " + job["location"]) if job.get("location") else ""}</li>'
        for job in listed
    )
    more_html = f'<p>…and {more} more on <a href="{escape(origin)}/jobs">JobsHub</a>.</p>' if more else ""
    html = (
        f"<p><strong>{escape(subject)}</strong></p><ol>{items}</ol>{more_html}"
        f'<p style="color:#777;font-size:12px"><a href="{escape(origin)}/alerts">Manage or stop these alerts</a></p>'
    )
    return subject, "\n".join(text_lines), html
