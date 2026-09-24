"""The jobs pages, rendered on the server so they work the same on a phone and a PC:

- /jobs              search + stats + the list; each row opens its job. Filters, sort and
                     page are plain GET parameters, so the URL *is* the list. On a PC
                     (Tailwind `lg`) the chosen job (?sel=<id>, else the first row) is shown
                     in a pane beside the list; app.js swaps it via /jobs/<id>/panel. On a
                     phone the pane is hidden and a row opens the job's own page.
- /jobs/<id>         one job (phones, shared links, alert messages). Back returns to the same
                     list and row (#job-<id>).
- /jobs/<id>/panel   the same job as an HTML fragment for the PC pane.
- /jobs/<id>/apply   records the click, then redirects to the employer's page.

Anyone sees a job's title, company, location, badges and date; the description and Apply
need a signed-in, verified account.
"""
from urllib.parse import quote, urlparse

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for

from jobhub_poc import config
from jobhub_poc.webapp.auth import access_state, login_url, verify_url
from jobhub_poc.webapp.job_text import format_description
from jobhub_poc.webapp.jobs_listing import (
    PAGE_SIZES,
    POSTED_WITHIN_OPTIONS,
    list_query_string,
    parse_list_args,
    present_job,
    query_jobs,
    record,
    safe_back_query,
    site_figures,
)

bp = Blueprint("jobs", __name__)


def _apply_url_ok(url):
    return bool(url) and urlparse(url).scheme in ("http", "https")


def _detail(conn, job_id, record_view):
    """Template context for one job (the page and the pane share _job_detail.html), or None
    if it's gone. Records a view for verified users when record_view is set."""
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        return None
    state = access_state()
    if state == "verified" and record_view:
        record(conn, row, "view_details")
    here = url_for("jobs.job_page", job_id=job_id)
    return {
        "job": present_job(row),
        "state": state,
        "description": format_description(row["description"]) if state == "verified" else None,
        "can_apply": _apply_url_ok(row["apply_url"]),
        "login_url": login_url(here),
        "register_url": f"{url_for('auth.register')}?next={quote(here, safe='/')}",
        "verify_url": verify_url(here),
    }


@bp.route("/jobs")
def list_jobs():
    # Old links (alert digests, sign-in `next`) were /jobs?job=<id>.
    old_link = request.args.get("job", "")
    if old_link.isdigit():
        return redirect(url_for("jobs.job_page", job_id=int(old_link)))

    conn = current_app.get_db()
    q = parse_list_args(request.args)
    result = query_jobs(conn, q)
    jobs = [present_job(r) for r in result.rows]
    list_qs = list_query_string(q, page=result.page)

    # The PC pane: the job asked for, else the first on this page. Only an explicit
    # ?sel= counts as a view -- the default one is never seen on a phone.
    sel = request.args.get("sel", "")
    selected = _detail(conn, int(sel), record_view=True) if sel.isdigit() else None
    if selected is None and jobs:
        selected = _detail(conn, jobs[0]["id"], record_view=False)

    return render_template(
        "jobs.html",
        wide=True,  # base.html: the list + pane need more than the default 5xl column
        q=q,
        jobs=jobs,
        result=result,
        first=(result.page - 1) * q.page_size + 1 if result.total else 0,
        last=min(result.page * q.page_size, result.total),
        list_qs=list_qs,
        prev_qs=list_query_string(q, page=result.page - 1) if result.page > 1 else None,
        next_qs=list_query_string(q, page=result.page + 1) if result.page < result.total_pages else None,
        selected=selected,
        site=site_figures(conn),
        popular=config.POPULAR_SEARCHES,
        filtered=q != parse_list_args({}),
        posted_within_options=POSTED_WITHIN_OPTIONS,
        page_sizes=PAGE_SIZES,
    )


@bp.route("/jobs/<int:job_id>")
def job_page(job_id):
    detail = _detail(current_app.get_db(), job_id, record_view=True)
    if detail is None:
        return render_template("job_missing.html"), 404
    back_qs = safe_back_query(request.args.get("back"))
    back_url = f"{url_for('jobs.list_jobs')}{'?' + back_qs if back_qs else ''}#job-{job_id}"
    return render_template("job.html", back_url=back_url, **detail)


@bp.route("/jobs/<int:job_id>/panel")
def job_panel(job_id):
    detail = _detail(current_app.get_db(), job_id, record_view=True)
    if detail is None:
        return render_template("_job_missing_panel.html"), 404
    return render_template("_job_panel.html", **detail)


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
