from flask import Blueprint, current_app, jsonify, request

from jobhub_poc.webapp.auth import access_state, login_url, verify_url
from jobhub_poc.webapp.jobs_listing import parse_list_args, query_jobs, record

bp = Blueprint("api", __name__)


@bp.route("/api/jobs")
def list_jobs_json():
    q = parse_list_args(request.args)
    result = query_jobs(current_app.get_db(), q)
    jobs = [
        {
            "id": r["id"],
            "title": r["title"],
            "company_name": r["company_name"],
            "location": r["location"],
            "employment_type": r["employment_type"],
            "is_remote": bool(r["is_remote"]),
            "first_seen_at": r["first_seen_at"],
            "posted_at": r["posted_at"],
        }
        for r in result.rows
    ]
    return jsonify({
        "jobs": jobs,
        "page": result.page,
        "page_size": q.page_size,
        "total": result.total,
        "total_pages": result.total_pages,
    })


# ---- job details: signed-in, verified users only (drives signups). The /jobs/<id> page
# (routes_jobs.py) is what the site itself uses; these stay for API callers. ----

def _gate(job_id):
    """None if the caller may see job details, else the JSON error response."""
    next_path = f"/jobs/{job_id}"
    state = access_state()
    if state == "anonymous":
        return jsonify({"code": "LOGIN_REQUIRED", "login_url": login_url(next_path)}), 401
    if state == "unverified":
        return jsonify({"code": "VERIFY_REQUIRED", "verify_url": verify_url(next_path)}), 403
    return None


@bp.route("/api/jobs/<int:job_id>")
def job_details(job_id):
    denied = _gate(job_id)
    if denied:
        return denied
    conn = current_app.get_db()
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if job is None:
        return jsonify({"code": "NOT_FOUND"}), 404
    record(conn, job, "view_details")
    return jsonify({
        "id": job["id"],
        "title": job["title"],
        "company_name": job["company_name"],
        "location": job["location"],
        "employment_type": job["employment_type"],
        "is_remote": bool(job["is_remote"]),
        "first_seen_at": job["first_seen_at"],
        "description": job["description"],
        "apply_url": job["apply_url"],
    })


@bp.route("/api/jobs/<int:job_id>/apply-click", methods=["POST"])
def apply_click(job_id):
    """Logs the click, then hands back the employer's URL for the browser to open."""
    denied = _gate(job_id)
    if denied:
        return denied
    conn = current_app.get_db()
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if job is None or not job["apply_url"]:
        return jsonify({"code": "NOT_FOUND"}), 404
    record(conn, job, "click_apply")
    return jsonify({"apply_url": job["apply_url"]})
