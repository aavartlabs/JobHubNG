"""The jobs list, shared by the /jobs page (routes_jobs.py) and GET /api/jobs
(routes_api.py): which query-string values are accepted, the query itself, the "posted"
label, and recording what signed-in users look at and apply to.

The list's state lives entirely in the URL (list_query_string), so a job page can link
back to exactly the list it was opened from (safe_back_query) and land on the same row
via #job-<id>."""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlencode

from flask import g

# Posted date when the source gave a usable one, else when we first saw the job.
POSTED_OR_SEEN = "COALESCE(posted_at, first_seen_at)"
SORTS = {
    "freshness": "first_seen_at DESC",
    "posted": f"{POSTED_OR_SEEN} DESC",
    "title": "title ASC",
}
POSTED_WITHIN_OPTIONS = [
    (0, "Any time"),
    (1, "Last 24 hours"),
    (3, "Last 3 days"),
    (7, "Last week"),
    (30, "Last month"),
]
PAGE_SIZES = (10, 25, 50, 100)
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
_MAX_TEXT = 100

# Re-opening the same job within this window isn't a new "viewed" signal.
VIEW_DEDUPE_WINDOW = timedelta(hours=1)


@dataclass(frozen=True)
class ListQuery:
    title: str = ""
    location: str = ""
    sort: str = "freshness"
    posted_within: int = 0
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE


def _positive_int(raw, default, maximum=None):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    if value < 1:
        return default
    return min(value, maximum) if maximum else value


def parse_list_args(args) -> ListQuery:
    """Only known values survive; anything else falls back to its default."""
    posted = str(args.get("posted_within", "") or "")
    return ListQuery(
        title=(args.get("title") or "").strip()[:_MAX_TEXT],
        location=(args.get("location") or "").strip()[:_MAX_TEXT],
        sort=args.get("sort") if args.get("sort") in SORTS else "freshness",
        posted_within=int(posted) if posted.isdigit() and int(posted) in dict(POSTED_WITHIN_OPTIONS) else 0,
        page=_positive_int(args.get("page"), 1),
        page_size=_positive_int(args.get("page_size"), DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE),
    )


def list_query_string(q: ListQuery, **changes) -> str:
    """The canonical query string for q (defaults left out), e.g. "title=sre&page=2"."""
    q = replace(q, **changes)
    defaults = ListQuery()
    pairs = [(k, getattr(q, k)) for k in ("title", "location", "sort", "posted_within", "page", "page_size")
             if getattr(q, k) != getattr(defaults, k)]
    return urlencode(pairs)


def safe_back_query(raw) -> str:
    """A job page's ?back= value, re-parsed so only list parameters come through: it can
    only ever point back at /jobs, never anywhere else."""
    parsed = parse_qs(raw or "", keep_blank_values=False)
    return list_query_string(parse_list_args({k: v[0] for k, v in parsed.items()}))


def query_jobs(conn, q: ListQuery, now=None):
    """(rows, total, page, total_pages) for q; page is clamped to the last page."""
    where = "WHERE 1=1"
    params: list = []
    if q.title:
        where += " AND title LIKE ?"
        params.append(f"%{q.title}%")
    if q.location:
        where += " AND location LIKE ?"
        params.append(f"%{q.location}%")
    if q.posted_within:
        now = now or datetime.now(timezone.utc)
        where += f" AND {POSTED_OR_SEEN} >= ?"
        params.append((now - timedelta(days=q.posted_within)).isoformat())

    total = conn.execute(f"SELECT COUNT(*) FROM jobs {where}", params).fetchone()[0]
    total_pages = max(1, (total + q.page_size - 1) // q.page_size)
    page = min(q.page, total_pages)
    rows = conn.execute(
        f"SELECT * FROM jobs {where} ORDER BY {SORTS[q.sort]} LIMIT ? OFFSET ?",
        [*params, q.page_size, (page - 1) * q.page_size],
    ).fetchall()
    return rows, total, page, total_pages


def _age(iso, now):
    try:
        then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return ""
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    days = (now - then).days
    if days < 1:
        return "today"
    if days < 14:
        return f"{days}d ago"
    if days < 60:
        return f"{days // 7}w ago"
    if days < 730:
        return f"{days // 30}mo ago"
    return f"{days // 365}y ago"


def posted_label(posted_at, first_seen_at, now=None):
    """"3d ago" from the source's posted date; without one, "seen 3d ago" from when we
    first found the job -- the same fallback the filter and sort use."""
    now = now or datetime.now(timezone.utc)
    if posted_at:
        return _age(posted_at, now)
    seen = _age(first_seen_at, now)
    return f"seen {seen}" if seen else ""


def record(conn, job, action):
    """Log a signed-in user's view_details / click_apply on job (a jobs row). Views of the
    same job within VIEW_DEDUPE_WINDOW count once."""
    now = datetime.now(timezone.utc)
    user_id = g.current_user["id"]
    if action == "view_details" and conn.execute(
        "SELECT 1 FROM job_interactions WHERE owner_auth_user_id = ? AND job_dedupe_key = ? "
        "AND action = 'view_details' AND created_at >= ?",
        (user_id, job["dedupe_key"], (now - VIEW_DEDUPE_WINDOW).isoformat()),
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
