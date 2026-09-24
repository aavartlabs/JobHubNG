"""Job alerts v2: filters (titles, locations, companies, keywords, work mode) plus which
of the owner's own verified contacts get the digest. No address is ever typed here:
digests go to the account's email / linked Telegram (alerts/contacts.py), looked up at
send time."""
import json
from datetime import datetime, timezone

from flask import Blueprint, current_app, g, redirect, render_template, request, url_for

from jobhub_poc.alerts.digest import describe_rule
from jobhub_poc.alerts.matcher import rule_from_row
from jobhub_poc.webapp import turnstile
from jobhub_poc.webapp.auth import login_required

bp = Blueprint("alerts", __name__)

LIST_FIELDS = ("titles", "locations", "companies", "keywords")
MAX_VALUES = 10
MAX_VALUE_LENGTH = 60
WORK_MODES = {"": None, "remote": "remote", "onsite": "onsite"}


class InvalidAlert(ValueError):
    pass


def _split(raw):
    values = []
    for item in (raw or "").split(","):
        item = " ".join(item.split()).lower()
        if item and item not in values:
            values.append(item)
    if len(values) > MAX_VALUES:
        raise InvalidAlert(f"Up to {MAX_VALUES} values per field, please.")
    if any(len(v) > MAX_VALUE_LENGTH for v in values):
        raise InvalidAlert(f"Each value must be {MAX_VALUE_LENGTH} characters or fewer.")
    return values


def parse_alert_form(form, telegram_linked=False):
    """Validated column values for a new alert, or InvalidAlert with a reason. Telegram
    delivery needs the owner's Telegram linked (auth-service's telegramVerified)."""
    lists = {field: _split(form.get(field)) for field in LIST_FIELDS}
    mode_raw = (form.get("work_mode") or "").strip().lower()
    if mode_raw not in WORK_MODES:
        raise InvalidAlert("Unknown work mode.")
    work_mode = WORK_MODES[mode_raw]
    if not any(lists.values()) and not work_mode:
        raise InvalidAlert("Pick at least one job title, location, company, keyword or a work mode.")
    notify_email = form.get("notify_email") == "on"
    notify_telegram = form.get("notify_telegram") == "on"
    if notify_telegram and not telegram_linked:
        raise InvalidAlert("Connect Telegram first to get alerts there -- or choose email.")
    if not (notify_email or notify_telegram):
        raise InvalidAlert("Choose email or Telegram (or both) for this alert.")
    return {**{k: json.dumps(v) for k, v in lists.items()}, "work_mode": work_mode,
            "notify_email": int(notify_email), "notify_telegram": int(notify_telegram)}


def _mask_email(email):
    name, _, domain = (email or "").partition("@")
    return f"{name[:2]}•••@{domain}" if domain else ""


def _telegram_label(user):
    username = user.get("telegramUsername")
    return f"@{username}" if username else "your linked account"


def _telegram_linked():
    return bool(g.current_user.get("telegramVerified"))


def _form_context():
    user = g.current_user
    return {"masked_email": _mask_email(user.get("email")), "telegram_label": _telegram_label(user),
            "telegram_linked": _telegram_linked()}


@bp.route("/alerts/register", methods=["GET", "POST"])
@login_required
def register():
    if request.method == "GET":
        return render_template("alerts_register.html", form={}, **_form_context())

    # Bot-checked even though only verified accounts get here: it triggers real messages.
    if not turnstile.verify(request.form.get("cf-turnstile-response"), "alert_register"):
        return render_template("alerts_register.html", form=request.form,
                               error="Bot check failed or expired. Please try again.", **_form_context()), 403
    try:
        values = parse_alert_form(request.form, telegram_linked=_telegram_linked())
    except InvalidAlert as exc:
        return render_template("alerts_register.html", form=request.form, error=str(exc), **_form_context()), 400

    conn = current_app.get_db()
    conn.execute(
        """INSERT INTO alert_subscriptions (owner_auth_user_id, titles, locations, companies, keywords,
                                            work_mode, notify_email, notify_telegram, is_active, created_at)
           VALUES (:owner, :titles, :locations, :companies, :keywords, :work_mode, :notify_email,
                   :notify_telegram, 1, :created_at)""",
        {**values, "owner": g.current_user["id"], "created_at": datetime.now(timezone.utc).isoformat()},
    )
    conn.commit()
    return redirect(url_for("alerts.list_alerts"))


@bp.route("/alerts")
@login_required
def list_alerts():
    """Only the current user's own alerts -- scoped by owner_auth_user_id."""
    conn = current_app.get_db()
    alerts = [
        {"row": row, "summary": describe_rule(rule_from_row(row))}
        for row in conn.execute(
            "SELECT * FROM alert_subscriptions WHERE owner_auth_user_id = ? ORDER BY created_at DESC",
            (g.current_user["id"],),
        )
    ]
    return render_template("alerts_list.html", alerts=alerts, telegram_linked=_telegram_linked())


def _owned_update(sub_id, sql):
    """Runs sql for (id, owner) only, so nobody can act on someone else's alert by id."""
    conn = current_app.get_db()
    conn.execute(sql, (sub_id, g.current_user["id"]))
    conn.commit()
    return redirect(url_for("alerts.list_alerts"))


@bp.route("/alerts/<int:sub_id>/pause", methods=["POST"])
@login_required
def pause(sub_id):
    return _owned_update(sub_id, "UPDATE alert_subscriptions SET is_active = 0 WHERE id = ? AND owner_auth_user_id = ?")


@bp.route("/alerts/<int:sub_id>/resume", methods=["POST"])
@login_required
def resume(sub_id):
    return _owned_update(sub_id, "UPDATE alert_subscriptions SET is_active = 1 WHERE id = ? AND owner_auth_user_id = ?")


@bp.route("/alerts/<int:sub_id>/delete", methods=["POST"])
@login_required
def delete(sub_id):
    conn = current_app.get_db()
    owned = conn.execute("SELECT 1 FROM alert_subscriptions WHERE id = ? AND owner_auth_user_id = ?",
                         (sub_id, g.current_user["id"])).fetchone()
    if owned:
        conn.execute("DELETE FROM alerts_sent WHERE subscription_id = ?", (sub_id,))
        conn.execute("DELETE FROM alert_subscriptions WHERE id = ?", (sub_id,))
        conn.commit()
    return redirect(url_for("alerts.list_alerts"))
