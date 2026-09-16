import re
from datetime import datetime, timezone

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

from jobhub_poc.webapp.auth import login_required

bp = Blueprint("alerts", __name__)

_PHONE_RE = re.compile(r"^\+?[0-9]{7,15}$")


@bp.route("/alerts/register", methods=["GET", "POST"])
@login_required
def register():
    if request.method == "GET":
        return render_template("alerts_register.html")

    phone = request.form.get("phone_number", "").strip()
    if not _PHONE_RE.match(phone):
        return render_template("alerts_register.html", error="Enter a valid phone number, e.g. +15551234567"), 400

    conn = current_app.get_db()
    conn.execute(
        """
        INSERT INTO alert_subscriptions
            (phone_number, title_keyword, location_keyword, created_by_user_id, is_active, created_at)
        VALUES (?, ?, ?, ?, 1, ?)
        """,
        (
            phone,
            request.form.get("title_keyword") or None,
            request.form.get("location_keyword") or None,
            session.get("user_id"),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    return redirect(url_for("jobs.list_jobs"))
