from flask import Blueprint, current_app, render_template, request

from jobhub_poc.webapp.auth import login_required

bp = Blueprint("jobs", __name__)


@bp.route("/jobs")
@login_required
def list_jobs():
    conn = current_app.get_db()
    title = request.args.get("title", "").strip()
    location = request.args.get("location", "").strip()

    query = "SELECT * FROM jobs WHERE 1=1"
    params: list[str] = []
    if title:
        query += " AND title LIKE ?"
        params.append(f"%{title}%")
    if location:
        query += " AND location LIKE ?"
        params.append(f"%{location}%")
    query += " ORDER BY first_seen_at DESC"

    jobs = conn.execute(query, params).fetchall()
    return render_template("jobs.html", jobs=jobs, title=title, location=location)
