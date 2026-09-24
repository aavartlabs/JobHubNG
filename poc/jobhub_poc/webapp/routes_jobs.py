"""The jobs pages, rendered on the server so they work the same on a phone and a PC:

- /jobs              the list: title, company, location, posted; each row opens its job.
                     Filters, sort and page are plain GET parameters, so the URL *is* the
                     list -- the browser's back button and the job page's Back link both
                     return to the same list, scrolled to the row (#job-<id>).
- /jobs/<id>         one job. Anyone sees title, company, location and date; the
                     description and Apply need a signed-in, verified account.
- /jobs/<id>/apply   records the click, then redirects to the employer's page (opened in
                     a new tab by the job page).
"""
from urllib.parse import quote, urlparse

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for

from jobhub_poc.webapp.auth import access_state, login_url, verify_url
from jobhub_poc.webapp.jobs_listing import (
    PAGE_SIZES,
    POSTED_WITHIN_OPTIONS,
    list_query_string,
    parse_list_args,
    posted_label,
    query_jobs,
    record,
    safe_back_query,
)

bp = Blueprint("jobs", __name__)


@bp.route("/jobs")
def list_jobs():
    # Old links (alert digests, sign-in `next`) were /jobs?job=<id>.
    old_link = request.args.get("job", "")
    if old_link.isdigit():
        return redirect(url_for("jobs.job_page", job_id=int(old_link)))

    q = parse_list_args(request.args)
    rows, total, page, total_pages = query_jobs(current_app.get_db(), q)
    jobs = [
        {
            "id": r["id"],
            "title": r["title"],
            "company": r["company_name"] or "",
            "location": r["location"] or "",
            "posted": posted_label(r["posted_at"], r["first_seen_at"]),
            "posted_on": (r["posted_at"] or r["first_seen_at"] or "")[:10],
        }
        for r in rows
    ]
    return render_template(
        "jobs.html",
        q=q,
        jobs=jobs,
        total=total,
        page=page,
        total_pages=total_pages,
        first=(page - 1) * q.page_size + 1 if total else 0,
        last=min(page * q.page_size, total),
        list_qs=list_query_string(q, page=page),
        prev_qs=list_query_string(q, page=page - 1) if page > 1 else None,
        next_qs=list_query_string(q, page=page + 1) if page < total_pages else None,
        posted_within_options=POSTED_WITHIN_OPTIONS,
        page_sizes=PAGE_SIZES,
    )


def _apply_url_ok(url):
    return bool(url) and urlparse(url).scheme in ("http", "https")


@bp.route("/jobs/<int:job_id>")
def job_page(job_id):
    conn = current_app.get_db()
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    back_qs = safe_back_query(request.args.get("back"))
    back_url = f"{url_for('jobs.list_jobs')}{'?' + back_qs if back_qs else ''}#job-{job_id}"
    if job is None:
        return render_template("job_missing.html"), 404

    state = access_state()
    if state == "verified":
        record(conn, job, "view_details")
    here = url_for("jobs.job_page", job_id=job_id)
    return render_template(
        "job.html",
        job=job,
        state=state,
        back_url=back_url,
        posted=posted_label(job["posted_at"], job["first_seen_at"]),
        can_apply=_apply_url_ok(job["apply_url"]),
        login_url=login_url(here),
        register_url=f"{url_for('auth.register')}?next={quote(here, safe='/')}",
        verify_url=verify_url(here),
    )


@bp.route("/jobs/<int:job_id>/apply")
def apply(job_id):
    here = url_for("jobs.job_page", job_id=job_id)
    state = access_state()
    if state == "anonymous":
        return redirect(login_url(here))
    if state == "unverified":
        return redirect(verify_url(here))
    conn = current_app.get_db()
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if job is None or not _apply_url_ok(job["apply_url"]):
        abort(404)
    record(conn, job, "click_apply")
    return redirect(job["apply_url"])
