"""A signed-in user's resume (/profile): upload (PDF/DOCX, with consent), automatic
structuring by the LLM (ai/llm.py, queued, see ai/worker.py), review and edit, download, delete.
The structured resume the user saves here is the single source of truth for matching and
tailoring -- nothing downstream may add facts that aren't in it.

All resume content is encrypted at rest (crypto.py); if RESUME_ENCRYPTION_KEY isn't set
the page says the feature is off and accepts nothing."""
import re
from datetime import datetime, timezone

from flask import Blueprint, Response, current_app, g, jsonify, redirect, render_template, request, url_for
from werkzeug.exceptions import RequestEntityTooLarge

from jobhub_poc import config, crypto, job_preferences, resume_consent, resume_review
from jobhub_poc.ai import llm, tasks
from jobhub_poc.resume_text import MIME, ResumeUnreadable, detect_kind, extract_text
from jobhub_poc.webapp.auth import login_required

bp = Blueprint("profile", __name__)


def _now():
    return datetime.now(timezone.utc).isoformat()


PAUSED = ("Resume features are paused for now: JobsHub isn't reading resumes, matching or "
          "tailoring. Search, alerts, saved jobs and your preferences all work as usual.")


def _resume_row(conn):
    return conn.execute("SELECT * FROM resumes WHERE owner_auth_user_id = ?", (g.current_user["id"],)).fetchone()


def _page(error=None, status=200, notice=None):
    conn = current_app.get_db()
    row = _resume_row(conn)
    structured, task = None, None
    ai_on = config.ai_features_on()
    if ai_on and row is not None and row["structured_enc"] and crypto.enabled():
        try:
            structured = crypto.decrypt_json(row["structured_enc"])
        except crypto.CryptoUnavailable:
            # Encrypted under a key the site no longer has: unreadable, but replaceable.
            current_app.logger.error("profile: can't decrypt stored resume for %s", g.current_user["id"])
            error = error or ("We can't read your stored resume any more (a site change). "
                              "Please upload it again, or delete it.")
    if row is not None and row["parse_status"] == "queued":
        task = conn.execute(
            "SELECT id, status FROM ai_tasks WHERE kind = 'parse_resume' AND owner_auth_user_id = ? "
            "ORDER BY id DESC LIMIT 1", (g.current_user["id"],)).fetchone()
    return render_template(
        "profile.html", resume=row, structured=structured, task=task, error=error, notice=notice,
        notes=resume_review.review(structured) if structured else {},
        section_titles={"basics": "Basics", "summary": "Summary", "skills": "Skills",
                        "experience": "Experience", "education": "Education", "links": "Links"},
        enabled=crypto.enabled(), ai_online=llm.available() if task else True, ai_on=ai_on, paused_text=PAUSED,
        consent_text=resume_consent.text(),
        # Always a form: anyone can set their "Jobs for you" roles and places by hand.
        prefs=(job_preferences.get(conn, g.current_user["id"])
               or (job_preferences.propose(structured) if structured else None)
               or {"roles": [], "locations": [], "include_remote": True}),
        consent_current=bool(row is not None and resume_consent.is_current(row["consent_at"])),
        max_mb=config.MAX_RESUME_BYTES // (1024 * 1024), max_bytes=config.MAX_RESUME_BYTES,
    ), status


@bp.app_errorhandler(RequestEntityTooLarge)
def too_large(_error):
    """Over Flask's MAX_CONTENT_LENGTH: say so on the profile page, not a bare 413.
    (app.js checks the size before uploading, so this is only the no-JS fallback.)"""
    message = f"That file is over {config.MAX_RESUME_BYTES // (1024 * 1024)} MB. Try a smaller PDF or a DOCX."
    if request.path == url_for("profile.upload") and getattr(g, "current_user", None):
        return _page(message, 413)
    return message, 413


@bp.route("/profile")
@login_required
def profile():
    return _page(notice=request.args.get("notice"))


@bp.route("/profile/resume", methods=["POST"])
@login_required
def upload():
    if not config.ai_features_on():  # nothing would read it: don't store resumes meanwhile
        return _page(PAUSED, 503)
    if not crypto.enabled():
        return _page("Resume upload isn't switched on yet.", 503)
    conn = current_app.get_db()
    previous = _resume_row(conn)
    # Consent is asked once per set of terms; replacing the file relies on the consent already
    # given, unless the terms changed since (resume_consent.py).
    agreed_before = bool(previous and resume_consent.is_current(previous["consent_at"]))
    if request.form.get("consent") != "on" and not agreed_before:
        return _page("Please confirm you agree to how we use your resume.", 400)
    file = request.files.get("resume")
    data = file.read(config.MAX_RESUME_BYTES + 1) if file else b""
    if not data:
        return _page("Choose a PDF or Word (.docx) file to upload.", 400)
    if len(data) > config.MAX_RESUME_BYTES:
        return _page(f"That file is over {config.MAX_RESUME_BYTES // (1024 * 1024)} MB.", 400)
    kind = detect_kind(data)
    if kind is None:
        return _page("Upload a PDF or Word (.docx) file.", 400)
    try:
        text = extract_text(data, kind)
    except ResumeUnreadable as exc:
        return _page(str(exc), 400)

    now = _now()
    consent_at = previous["consent_at"] if agreed_before else now
    filename = re.sub(r"[^\w.\- ]", "_", (file.filename or f"resume.{kind}"))[:120]
    conn.execute(
        """INSERT INTO resumes (owner_auth_user_id, filename, mime, size_bytes, file_enc, text_enc,
                                structured_enc, parse_status, parse_error, edited_at, consent_at, uploaded_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, NULL, 'queued', NULL, NULL, ?, ?, ?)
           ON CONFLICT (owner_auth_user_id) DO UPDATE SET filename = excluded.filename, mime = excluded.mime,
             size_bytes = excluded.size_bytes, file_enc = excluded.file_enc, text_enc = excluded.text_enc,
             structured_enc = NULL, parse_status = 'queued', parse_error = NULL, edited_at = NULL,
             consent_at = excluded.consent_at, uploaded_at = excluded.uploaded_at, updated_at = excluded.updated_at""",
        (g.current_user["id"], filename, MIME[kind], len(data), crypto.encrypt(data),
         crypto.encrypt(text.encode()), consent_at, now, now))
    conn.commit()
    tasks.enqueue(conn, "parse_resume", owner=g.current_user["id"], priority=10)
    return redirect(url_for("profile.profile"))


@bp.route("/profile/preferences", methods=["POST"])
@login_required
def preferences():
    """The roles and places /jobs shows by default ("Jobs for you")."""
    split = lambda raw: [x.strip() for x in (raw or "").split(",") if x.strip()]  # noqa: E731
    job_preferences.save(current_app.get_db(), g.current_user["id"], split(request.form.get("roles")),
                         split(request.form.get("locations")), request.form.get("include_remote") == "on")
    return redirect(url_for("profile.profile", notice="Saved. /jobs now shows jobs for these roles and places."))


@bp.route("/profile/consent", methods=["POST"])
@login_required
def consent():
    """Agree to changed terms without uploading again; AI work on the resume resumes."""
    if request.form.get("consent") != "on":
        return _page("Please tick the box to agree, or delete your resume.", 400)
    conn = current_app.get_db()
    row = _resume_row(conn)
    if row is None:
        return redirect(url_for("profile.profile"))
    conn.execute("UPDATE resumes SET consent_at = ?, updated_at = ? WHERE owner_auth_user_id = ?",
                 (_now(), _now(), g.current_user["id"]))
    if row["parse_status"] == "failed" and not row["structured_enc"]:
        conn.execute("UPDATE resumes SET parse_status = 'queued', parse_error = NULL WHERE owner_auth_user_id = ?",
                     (g.current_user["id"],))
        conn.commit()
        tasks.enqueue(conn, "parse_resume", owner=g.current_user["id"], priority=10)
    conn.commit()
    return redirect(url_for("profile.profile", notice="Thanks. Your resume is back in use."))


def _lines(value, limit, width):
    return [re.sub(r"\s+", " ", x).strip()[:width] for x in (value or "").splitlines() if x.strip()][:limit]


def structured_from_form(form, previous):
    """The edit form -> the structured resume. Bullets the user kept unchanged keep their
    "unverified" flag; anything they typed is theirs (they vouch for it)."""
    old_bullets = {b["text"]: b.get("unverified", False)
                   for r in (previous or {}).get("roles", []) for b in r["bullets"]}
    roles = []
    n = 0
    for i in range(int(form.get("role_count", 0) or 0) + 1):
        title = form.get(f"role-{i}-title", "").strip()[:120]
        company = form.get(f"role-{i}-company", "").strip()[:120]
        bullet_texts = _lines(form.get(f"role-{i}-bullets"), 30, 400)
        if form.get(f"role-{i}-remove") == "on" or not (title or company or bullet_texts):
            continue
        n += 1
        roles.append({
            "id": f"r{n}", "title": title, "company": company,
            "location": form.get(f"role-{i}-location", "").strip()[:120],
            "start": form.get(f"role-{i}-start", "").strip()[:20], "end": form.get(f"role-{i}-end", "").strip()[:20],
            "bullets": [{"id": f"r{n}b{j}", "text": t, "unverified": old_bullets.get(t, False)}
                        for j, t in enumerate(bullet_texts, 1)],
        })
    skills = []
    for s in re.split(r"[,\n]", form.get("skills", "")):
        s = s.strip()[:60]
        if s and s.lower() not in (x.lower() for x in skills):
            skills.append(s)
    return {
        "name": form.get("name", "").strip()[:120], "headline": form.get("headline", "").strip()[:160],
        "location": form.get("location", "").strip()[:120], "summary": form.get("summary", "").strip()[:1200],
        "skills": skills[:60], "links": _lines(form.get("links"), 6, 200), "roles": roles,
        "education": _lines(form.get("education"), 10, 200),
    }


@bp.route("/profile/resume/save", methods=["POST"])
@login_required
def save():
    if not config.ai_features_on():
        return redirect(url_for("profile.profile"))
    conn = current_app.get_db()
    row = _resume_row(conn)
    if row is None or not crypto.enabled():
        return redirect(url_for("profile.profile"))
    try:
        previous = crypto.decrypt_json(row["structured_enc"]) if row["structured_enc"] else None
    except crypto.CryptoUnavailable:
        previous = None
    structured = structured_from_form(request.form, previous)
    now = _now()
    conn.execute("UPDATE resumes SET structured_enc = ?, parse_status = 'done', edited_at = ?, updated_at = ? "
                 "WHERE owner_auth_user_id = ?", (crypto.encrypt_json(structured), now, now, g.current_user["id"]))
    conn.commit()
    return redirect(url_for("profile.profile", notice="Saved."))


@bp.route("/profile/resume/file")
@login_required
def download():
    row = _resume_row(current_app.get_db())
    if row is None:
        return redirect(url_for("profile.profile"))
    try:
        data = crypto.decrypt(row["file_enc"])
    except crypto.CryptoUnavailable:
        return redirect(url_for("profile.profile"))
    return Response(data, mimetype=row["mime"],
                    headers={"Content-Disposition": f'attachment; filename="{row["filename"]}"',
                             "Cache-Control": "no-store"})


def purge_user_resume_data(conn, user_id):
    """Everything resume-derived for a user (their delete button, and admin deletion)."""
    conn.execute("DELETE FROM resumes WHERE owner_auth_user_id = ?", (user_id,))
    conn.execute("DELETE FROM ai_tasks WHERE owner_auth_user_id = ?", (user_id,))
    conn.execute("DELETE FROM tailored_resumes WHERE owner_auth_user_id = ?", (user_id,))
    conn.execute("DELETE FROM match_evidence WHERE owner_auth_user_id = ?", (user_id,))
    conn.commit()


@bp.route("/profile/resume/delete", methods=["POST"])
@login_required
def delete():
    purge_user_resume_data(current_app.get_db(), g.current_user["id"])
    return redirect(url_for("profile.profile", notice="Your resume has been deleted."))


@bp.route("/ai/tasks/<int:task_id>")
@login_required
def task_status(task_id):
    task = tasks.get(current_app.get_db(), task_id, g.current_user["id"])
    if task is None:
        return jsonify({"code": "NOT_FOUND"}), 404
    return jsonify({"status": task["status"], "ai_online": llm.available() if task["status"] == "queued" else True})
