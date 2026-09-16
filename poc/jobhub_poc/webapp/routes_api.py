from flask import Blueprint, current_app, jsonify, request

from jobhub_poc.webapp.auth import login_required

bp = Blueprint("api", __name__)

_SORTS = {
    "freshness": "first_seen_at DESC",
    "title": "title ASC",
}


@bp.route("/api/jobs")
@login_required
def list_jobs_json():
    conn = current_app.get_db()
    title = request.args.get("title", "").strip()
    location = request.args.get("location", "").strip()
    sort = _SORTS.get(request.args.get("sort", "freshness"), _SORTS["freshness"])

    query = "SELECT * FROM jobs WHERE 1=1"
    params: list[str] = []
    if title:
        query += " AND title LIKE ?"
        params.append(f"%{title}%")
    if location:
        query += " AND location LIKE ?"
        params.append(f"%{location}%")
    query += f" ORDER BY {sort}"

    rows = conn.execute(query, params).fetchall()
    jobs = [
        {
            "id": r["id"],
            "title": r["title"],
            "company_name": r["company_name"],
            "location": r["location"],
            "employment_type": r["employment_type"],
            "is_remote": bool(r["is_remote"]),
            "apply_url": r["apply_url"],
            "first_seen_at": r["first_seen_at"],
        }
        for r in rows
    ]
    return jsonify({"count": len(jobs), "jobs": jobs})
