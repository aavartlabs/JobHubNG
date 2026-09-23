import re
from datetime import datetime, timezone

from flask import Blueprint, current_app, g, redirect, render_template, request, url_for

from jobhub_poc.webapp import turnstile
from jobhub_poc.webapp.auth import login_required

bp = Blueprint("alerts", __name__)

_PHONE_RE = re.compile(r"^\+?[0-9]{7,15}$")


@bp.route("/alerts/register", methods=["GET", "POST"])
@login_required
def register():
    if request.method == "GET":
        return render_template("alerts_register.html")

    # This form picks which WhatsApp number receives alerts, so it's bot-checked even
    # though only verified accounts can reach it.
    if not turnstile.verify(request.form.get("cf-turnstile-response"), "alert_register"):
        return render_template("alerts_register.html", error="Bot check failed or expired. Please try again."), 403

    phone = request.form.get("phone_number", "").strip()
    if not _PHONE_RE.match(phone):
        return render_template("alerts_register.html", error="Enter a valid phone number, e.g. +15551234567"), 400

    conn = current_app.get_db()
    conn.execute(
        """
        INSERT INTO alert_subscriptions
            (phone_number, title_keyword, location_keyword, owner_auth_user_id, is_active, created_at)
        VALUES (?, ?, ?, ?, 1, ?)
        """,
        (
            phone,
            request.form.get("title_keyword") or None,
            request.form.get("location_keyword") or None,
            g.current_user["id"],
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    return redirect(url_for("alerts.list_alerts"))


@bp.route("/alerts")
@login_required
def list_alerts():
    """Lists only the current user's own subscriptions -- scoped by owner_auth_user_id,
    never all subscriptions, so one user can never see another's alerts."""
    conn = current_app.get_db()
    subscriptions = conn.execute(
        "SELECT * FROM alert_subscriptions WHERE owner_auth_user_id = ? ORDER BY created_at DESC",
        (g.current_user["id"],),
    ).fetchall()
    return render_template("alerts_list.html", subscriptions=subscriptions)


@bp.route("/alerts/<int:sub_id>/deactivate", methods=["POST"])
@login_required
def deactivate(sub_id):
    """Scoped to (id AND owner_auth_user_id) so a user can never deactivate another
    user's subscription, even by guessing/incrementing an id."""
    conn = current_app.get_db()
    conn.execute(
        "UPDATE alert_subscriptions SET is_active = 0 WHERE id = ? AND owner_auth_user_id = ?",
        (sub_id, g.current_user["id"]),
    )
    conn.commit()
    return redirect(url_for("alerts.list_alerts"))
