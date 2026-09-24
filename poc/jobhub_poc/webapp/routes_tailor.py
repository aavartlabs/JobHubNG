"""The apply kit: a signed-in user's resume tailored for one job (tailoring.py), reviewed
and edited here, then downloaded to apply with -- and their original resume in the same
formats.

- POST /jobs/<id>/tailor           queue the tailoring (again, if there already is one)
- GET  /jobs/<id>/tailor           review: what changed and what was put back and why, an
                                   edit form, downloads, the cover note
- GET  /jobs/<id>/tailor/status    for app.js while it's being made (202 until ready)
- POST /jobs/<id>/tailor/save      the user's edits (theirs to vouch for, as on /profile)
- GET  /jobs/<id>/tailor/resume.docx, /jobs/<id>/tailor/print   the tailored resume
- GET  /profile/resume.docx, /profile/print                       the checked original

Tailored resumes are resume content: encrypted at rest like resumes (crypto.py)."""
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import Blueprint, Response, abort, current_app, g, redirect, render_template, request, url_for

from jobhub_poc import crypto, resume_render, tailoring
from jobhub_poc.ai import ollama, tasks
from jobhub_poc.webapp.auth import login_required
from jobhub_poc.webapp.jobs_listing import present_job

bp = Blueprint("tailor", __name__)


def _resume(conn, user_id):
    row = conn.execute("SELECT structured_enc FROM resumes WHERE owner_auth_user_id = ?", (user_id,)).fetchone()
    if row is None or not row["structured_enc"] or not crypto.enabled():
        return None
    try:
        return crypto.decrypt_json(row["structured_enc"])
    except crypto.CryptoUnavailable:
        return None


def _tailored(conn, user_id, key):
    row = conn.execute("SELECT * FROM tailored_resumes WHERE owner_auth_user_id = ? AND job_dedupe_key = ?",
                       (user_id, key)).fetchone()
    if row is None or not crypto.enabled():
        return row, None
    try:
        return row, crypto.decrypt_json(row["data_enc"])
    except crypto.CryptoUnavailable:
        return row, None


def _pending(conn, user_id, key):
    return conn.execute("SELECT 1 FROM ai_tasks WHERE kind = 'tailor' AND owner_auth_user_id = ? AND ref = ? "
                        "AND status IN ('queued', 'running')", (user_id, key)).fetchone() is not None


def tailor_state(conn, user_id, key):
    """For the apply kit on a job: "no_resume" | "pending" | "ready" | "none"."""
    if _resume(conn, user_id) is None:
        return "no_resume"
    if _pending(conn, user_id, key):
        return "pending"
    row = conn.execute("SELECT 1 FROM tailored_resumes WHERE owner_auth_user_id = ? AND job_dedupe_key = ?",
                       (user_id, key)).fetchone()
    return "ready" if row else "none"


def _job_or_404(conn, job_id):
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        abort(404)
    return row


@bp.route("/jobs/<int:job_id>/tailor", methods=["POST"])
@login_required
def start(job_id):
    conn = current_app.get_db()
    row = _job_or_404(conn, job_id)
    if _resume(conn, g.current_user["id"]) is not None:
        tasks.enqueue(conn, "tailor", owner=g.current_user["id"], ref=row["dedupe_key"], priority=8)
    return redirect(url_for("tailor.review", job_id=job_id))


@bp.route("/jobs/<int:job_id>/tailor")
@login_required
def review(job_id):
    conn = current_app.get_db()
    row = _job_or_404(conn, job_id)
    user_id = g.current_user["id"]
    record, tailored = _tailored(conn, user_id, row["dedupe_key"])
    pending = _pending(conn, user_id, row["dedupe_key"])
    return render_template(
        "tailor.html", job=present_job(row), resume=_resume(conn, user_id), record=record, tailored=tailored,
        can_apply=urlparse(row["apply_url"] or "").scheme in ("http", "https"),
        pending=pending, ai_online=ollama.available() if pending else True,
        contact=(tailored or {}).get("contact") or g.current_user.get("email", ""),
        notice=request.args.get("notice"))


@bp.route("/jobs/<int:job_id>/tailor/status")
@login_required
def status(job_id):
    conn = current_app.get_db()
    row = _job_or_404(conn, job_id)
    if _pending(conn, g.current_user["id"], row["dedupe_key"]):
        return render_template("_tailor_pending.html", job=present_job(row), ai_online=ollama.available()), 202
    return render_template("_tailor_pending.html", job=present_job(row), done=True), 200


@bp.route("/jobs/<int:job_id>/tailor/save", methods=["POST"])
@login_required
def save(job_id):
    conn = current_app.get_db()
    row = _job_or_404(conn, job_id)
    user_id = g.current_user["id"]
    _record, tailored = _tailored(conn, user_id, row["dedupe_key"])
    if tailored is None:
        return redirect(url_for("tailor.review", job_id=job_id))
    edited = tailoring.from_form(request.form, tailored)
    conn.execute("UPDATE tailored_resumes SET data_enc = ?, status = 'edited', updated_at = ? "
                 "WHERE owner_auth_user_id = ? AND job_dedupe_key = ?",
                 (crypto.encrypt_json(edited), datetime.now(timezone.utc).isoformat(), user_id, row["dedupe_key"]))
    conn.commit()
    return redirect(url_for("tailor.review", job_id=job_id, notice="Saved."))


def _docx_response(resume, suffix):
    return Response(resume_render.to_docx(resume),
                    mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{resume_render.filename(resume, suffix)}"',
                             "Cache-Control": "no-store"})


def _printable(resume):
    html = render_template("resume_print.html", resume=resume, dates=resume_render.dates)
    return Response(html, headers={"Cache-Control": "no-store"})


def _job_and_tailored(job_id):
    """The job row and its tailored resume (None if there isn't one), with the contact line
    defaulting to the account's email, as on the review page."""
    conn = current_app.get_db()
    row = _job_or_404(conn, job_id)
    tailored = _tailored(conn, g.current_user["id"], row["dedupe_key"])[1]
    if tailored is not None:
        tailored = {**tailored, "contact": tailored.get("contact") or g.current_user.get("email", "")}
    return row, tailored


@bp.route("/jobs/<int:job_id>/tailor/resume.docx")
@login_required
def tailored_docx(job_id):
    row, tailored = _job_and_tailored(job_id)
    if tailored is None:
        return redirect(url_for("tailor.review", job_id=job_id))
    company = (row["company_name"] or "").strip()
    return _docx_response(tailored, f"for-{company}" if company else "tailored")


@bp.route("/jobs/<int:job_id>/tailor/print")
@login_required
def tailored_print(job_id):
    _row, tailored = _job_and_tailored(job_id)
    if tailored is None:
        return redirect(url_for("tailor.review", job_id=job_id))
    return _printable(tailored)


def _original():
    resume = _resume(current_app.get_db(), g.current_user["id"])
    return {**resume, "contact": g.current_user.get("email", "")} if resume is not None else None


@bp.route("/profile/resume.docx")
@login_required
def original_docx():
    resume = _original()
    return _docx_response(resume, "") if resume else redirect(url_for("profile.profile"))


@bp.route("/profile/print")
@login_required
def original_print():
    resume = _original()
    return _printable(resume) if resume else redirect(url_for("profile.profile"))
