from flask import Blueprint, current_app, jsonify, request

bp = Blueprint("api", __name__)

_SORTS = {
    "freshness": "first_seen_at DESC",
    "title": "title ASC",
}
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
            "apply_url": r["apply_url"],
            "description": r["description"],
            "first_seen_at": r["first_seen_at"],
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
