from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, g, jsonify, request

from jobhub_poc.webapp.auth import access_state, login_url, verify_url

bp = Blueprint("api", __name__)

# Posted date when the source gave a usable one, else when we first saw the job.
_POSTED_OR_SEEN = "COALESCE(posted_at, first_seen_at)"
_SORTS = {
    "freshness": "first_seen_at DESC",
    "posted": f"{_POSTED_OR_SEEN} DESC",
    "title": "title ASC",
}
_POSTED_WITHIN_DAYS = {1, 3, 7, 30}
_DEFAULT_PAGE_SIZE = 25
_MAX_PAGE_SIZE = 100


def _positive_int(raw: str | None, default: int, maximum: int | None = None) -> int:
    try:
        value = int(raw)
        if value < 1:
            return default
    except (TypeError, ValueError):
        return default
    return min(value, maximum) if maximum else value


@bp.route("/api/jobs")
def list_jobs_json():
    conn = current_app.get_db()
    title = request.args.get("title", "").strip()
    location = request.args.get("location", "").strip()
    sort = _SORTS.get(request.args.get("sort", "freshness"), _SORTS["freshness"])
    page = _positive_int(request.args.get("page"), default=1)
    page_size = _positive_int(request.args.get("page_size"), default=_DEFAULT_PAGE_SIZE, maximum=_MAX_PAGE_SIZE)

    where = "WHERE 1=1"
    params: list[str] = []
    if title:
        where += " AND title LIKE ?"
        params.append(f"%{title}%")
    if location:
        where += " AND location LIKE ?"
        params.append(f"%{location}%")
    posted_within = request.args.get("posted_within", "")
    if posted_within.isdigit() and int(posted_within) in _POSTED_WITHIN_DAYS:
        where += f" AND {_POSTED_OR_SEEN} >= ?"
        params.append((datetime.now(timezone.utc) - timedelta(days=int(posted_within))).isoformat())

    total = conn.execute(f"SELECT COUNT(*) FROM jobs {where}", params).fetchone()[0]
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, total_pages)

    rows = conn.execute(
        f"SELECT * FROM jobs {where} ORDER BY {sort} LIMIT ? OFFSET ?",
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()

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
        for r in rows
    ]
    return jsonify({
        "jobs": jobs,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    })


# ---- job details: signed-in, verified users only (drives signups) ----

# Re-opening the same job's details within this window isn't a new signal.
_VIEW_DEDUPE_WINDOW = timedelta(hours=1)


def _gate(job_id):
    """None if the caller may see job details, else the JSON error response."""
    next_path = f"/jobs?job={job_id}"
    state = access_state()
    if state == "anonymous":
        return jsonify({"code": "LOGIN_REQUIRED", "login_url": login_url(next_path)}), 401
    if state == "unverified":
        return jsonify({"code": "VERIFY_REQUIRED", "verify_url": verify_url(next_path)}), 403
    return None


def _record(conn, job, action):
    now = datetime.now(timezone.utc)
    user_id = g.current_user["id"]
    if action == "view_details" and conn.execute(
        "SELECT 1 FROM job_interactions WHERE owner_auth_user_id = ? AND job_dedupe_key = ? "
        "AND action = 'view_details' AND created_at >= ?",
        (user_id, job["dedupe_key"], (now - _VIEW_DEDUPE_WINDOW).isoformat()),
    ).fetchone():
        return
    conn.execute(
        """
        INSERT INTO job_interactions
            (owner_auth_user_id, job_dedupe_key, job_title, job_company, job_apply_url, action, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, job["dedupe_key"], job["title"], job["company_name"], job["apply_url"], action, now.isoformat()),
    )
    conn.commit()


@bp.route("/api/jobs/<int:job_id>")
def job_details(job_id):
    denied = _gate(job_id)
    if denied:
        return denied
    conn = current_app.get_db()
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if job is None:
        return jsonify({"code": "NOT_FOUND"}), 404
    _record(conn, job, "view_details")
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
    _record(conn, job, "click_apply")
    return jsonify({"apply_url": job["apply_url"]})
