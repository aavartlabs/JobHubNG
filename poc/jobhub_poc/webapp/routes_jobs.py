from flask import Blueprint, render_template

from jobhub_poc.webapp.auth import login_required

bp = Blueprint("jobs", __name__)


@bp.route("/jobs")
@login_required
def list_jobs():
    """Serves the page shell; the TypeScript bundle (static/app.js) fetches
    /api/jobs (see routes_api.py) and renders rows client-side."""
    return render_template("jobs.html")
