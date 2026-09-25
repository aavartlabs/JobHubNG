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
- /jobs/<id>/save, /jobs/<id>/unsave (POST), /saved, /saved/remove (POST): a signed-in
                     user's saved jobs. Plain forms that redirect back; app.js calls them
                     with Accept: application/json to toggle in place.

Anyone sees a job's title, company, location, badges and date; the description and Apply
need a signed-in, verified account.
"""
from urllib.parse import quote, urlparse

from flask import Blueprint, abort, current_app, g, jsonify, redirect, render_template, request, url_for

from jobhub_poc import config, crypto, job_requirements, match_evidence, matching
from jobhub_poc.job_links import human_url
from jobhub_poc.ai import llm, tasks
from jobhub_poc.webapp.auth import access_state, login_required, login_url, verify_url
from jobhub_poc.webapp.job_text import format_description
from jobhub_poc.webapp.jobs_listing import (
    PAGE_SIZES,
    POSTED_WITHIN_OPTIONS,
    TRACK_STATUSES,
    list_query_string,
    parse_list_args,
    present_job,
    query_jobs,
    record,
    safe_back_query,
    save_job,
    saved_jobs,
    saved_keys,
    set_status,
    site_figures,
    track_state,
    unsave_job,
)
from jobhub_poc.webapp.routes_tailor import tailor_state

bp = Blueprint("jobs", __name__)


def _apply_url_ok(url):
    return bool(url) and urlparse(url).scheme in ("http", "https")


def _user_id():
    """The signed-in, verified user's id, else None (saving needs a verified account)."""
    return g.current_user["id"] if access_state() == "verified" else None


def _user_resume(conn):
    """The signed-in, verified user's checked resume (structured), or None."""
    user_id = _user_id()
    if not user_id or not crypto.enabled():
        return None
    row = conn.execute("SELECT structured_enc FROM resumes WHERE owner_auth_user_id = ?", (user_id,)).fetchone()
    if row is None or not row["structured_enc"]:
        return None
    try:
        return crypto.decrypt_json(row["structured_enc"])
    except crypto.CryptoUnavailable:
        return None


def _match_context(conn, resume, job, priority):
    """{"match_state": "ready"|"pending"|"no_resume"|None, "match": result or None}. Queues
    what's missing: the job's reading (job_reading.py), then Jev's judgment of this resume
    against it (match_evidence.py); plain matching when Jev can't be used."""
    if _user_id() is None:
        return {"match_state": None, "match": None}
    if resume is None:
        return {"match_state": "no_resume", "match": None}
    reqs = job_requirements.get_many(conn, [job["key"]]).get(job["key"])
    if reqs is None:
        tasks.enqueue(conn, "extract_job", ref=job["key"], priority=priority)
        return {"match_state": "pending", "match": None}
    state, evidence = match_evidence.state(conn, _user_id(), job["key"], resume, reqs, priority)
    if state == "pending":
        return {"match_state": "pending", "match": None}
    return {"match_state": "ready", "match": matching.match(resume, reqs, job, evidence)}


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
    job = present_job(row)
    user_id = _user_id()
    track_status, clicked_apply = track_state(conn, user_id, job["key"])
    return {
        **_match_context(conn, _user_resume(conn), job, priority=5),
        "tailor_state": tailor_state(conn, user_id, job["key"]) if user_id else None,
        "track_status": track_status,
        "clicked_apply": clicked_apply,
        "track_statuses": TRACK_STATUSES,
        "job": job,
        "saved": bool(saved_keys(conn, _user_id(), [job["key"]])),
        "share_url": f"{config.WEB_ORIGIN.rstrip('/')}{here}",
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
    saved = saved_keys(conn, _user_id(), [j["key"] for j in jobs])
    for j in jobs:
        j["saved"] = j["key"] in saved
    # Match badges for users with a resume; jobs not analysed yet are queued behind any job
    # someone is looking at right now (priority 1 < 5).
    resume = _user_resume(conn)
    if resume is not None:
        reqs = job_requirements.get_many(conn, [j["key"] for j in jobs])
        for j in jobs:
            if j["key"] in reqs:
                state, evidence = match_evidence.state(conn, _user_id(), j["key"], resume, reqs[j["key"]], 1)
                if state != "pending":
                    fit = matching.match(resume, reqs[j["key"]], j, evidence)
                    j["match"] = {"score": fit["score"], "verdict": fit["verdict"], "label": fit["label"]}
            else:
                tasks.enqueue(conn, "extract_job", ref=j["key"], priority=1)
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
    return redirect(human_url(job["apply_url"]))


# ---- saved jobs ----

def _safe_next(raw, default):
    """Only same-site paths: "/..." but not "//..." or anything with a backslash."""
    if isinstance(raw, str) and raw.startswith("/") and not raw.startswith("//") and "\\" not in raw:
        return raw
    return default


def _wants_json():
    return request.accept_mimetypes.best == "application/json"


def _needs_account(job_id):
    """None if the caller may save, else the response sending them to sign in / verify."""
    state = access_state()
    if state == "verified":
        return None
    here = url_for("jobs.job_page", job_id=job_id)
    target = login_url(here) if state == "anonymous" else verify_url(here)
    if _wants_json():
        return jsonify({"code": "LOGIN_REQUIRED" if state == "anonymous" else "VERIFY_REQUIRED",
                        "url": target}), 401 if state == "anonymous" else 403
    return redirect(target)


def _toggle(job_id, save):
    denied = _needs_account(job_id)
    if denied:
        return denied
    conn = current_app.get_db()
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if job is None:
        abort(404)
    if save:
        save_job(conn, g.current_user["id"], job)
    else:
        unsave_job(conn, g.current_user["id"], job["dedupe_key"])
    if _wants_json():
        return jsonify({"saved": save})
    return redirect(_safe_next(request.form.get("next"), url_for("jobs.job_page", job_id=job_id)))


@bp.route("/jobs/<int:job_id>/save", methods=["POST"])
def save(job_id):
    return _toggle(job_id, True)


@bp.route("/jobs/<int:job_id>/unsave", methods=["POST"])
def unsave(job_id):
    return _toggle(job_id, False)


@bp.route("/jobs/<int:job_id>/status", methods=["POST"])
def set_track_status(job_id):
    """The tracker: "Yes, I applied", or a status change. Saves the job if it isn't yet."""
    denied = _needs_account(job_id)
    if denied:
        return denied
    conn = current_app.get_db()
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if job is None:
        abort(404)
    set_status(conn, g.current_user["id"], job["dedupe_key"], request.form.get("status", ""), job=job)
    return redirect(_safe_next(request.form.get("next"), url_for("jobs.job_page", job_id=job_id)))


@bp.route("/saved/status", methods=["POST"])
@login_required
def saved_status():
    """Status change from My jobs -- works for jobs no longer listed, too (by key)."""
    set_status(current_app.get_db(), g.current_user["id"], request.form.get("key", ""), request.form.get("status", ""))
    return redirect(_safe_next(request.form.get("next"), url_for("jobs.saved")))


@bp.route("/saved")
@login_required
def saved():
    """My jobs: saved jobs and where each application stands (?status= filters)."""
    wanted = request.args.get("status", "")
    if wanted not in TRACK_STATUSES:
        wanted = ""
    items, counts = [], {}
    for saved_row, job in saved_jobs(current_app.get_db(), g.current_user["id"]):
        status = saved_row["status"] or "saved"
        counts[status] = counts.get(status, 0) + 1
        if wanted and status != wanted:
            continue
        if job is not None:
            item = present_job(job)
        else:  # purged since it was saved: show what was saved
            item = {"id": None, "key": saved_row["job_dedupe_key"], "title": saved_row["job_title"],
                    "company": saved_row["job_company"] or "", "location": saved_row["job_location"] or ""}
        item["saved_on"] = saved_row["saved_at"][:10]
        item["status"] = status
        items.append(item)
    return render_template("saved.html", items=items, counts=counts, wanted=wanted, statuses=TRACK_STATUSES)


@bp.route("/saved/remove", methods=["POST"])
@login_required
def saved_remove():
    unsave_job(current_app.get_db(), g.current_user["id"], request.form.get("key", ""))
    return redirect(url_for("jobs.saved"))


@bp.route("/jobs/<int:job_id>/match")
@login_required
def job_match(job_id):
    """The "Your match" card alone, for app.js to refresh while the job is being analysed.
    202 while it's still pending."""
    conn = current_app.get_db()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        abort(404)
    job = present_job(row)
    context = _match_context(conn, _user_resume(conn), job, priority=5)
    html = render_template("_match.html", job=job, ai_online=llm.available(), **context)
    return html, 202 if context["match_state"] == "pending" else 200
