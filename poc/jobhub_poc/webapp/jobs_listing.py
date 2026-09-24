"""The jobs list, shared by the /jobs page (routes_jobs.py) and GET /api/jobs
(routes_api.py): which query-string values are accepted, the query itself, the "posted"
label, and recording what signed-in users look at and apply to.

The list's state lives entirely in the URL (list_query_string), so a job page can link
back to exactly the list it was opened from (safe_back_query) and land on the same row
via #job-<id>."""
import hashlib
import json
import re
import time
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
WORK_MODES = {"remote": 1, "onsite": 0}
PAGE_SIZES = (10, 25, 50, 100)
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
_MAX_TEXT = 100

# Re-opening the same job within this window isn't a new "viewed" signal.
VIEW_DEDUPE_WINDOW = timedelta(hours=1)
# A job is "New" for this long after JobsHub first saw it.
NEW_WINDOW = timedelta(hours=24)


_PARAMS = ("q", "location", "work_mode", "sort", "posted_within", "page", "page_size")


@dataclass(frozen=True)
class ListQuery:
    q: str = ""                 # title or company contains
    location: str = ""
    work_mode: str = ""         # "", "remote" or "onsite"
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
        # `title` is the pre-2026-09-24 name for q; old links and bookmarks still work.
        q=(args.get("q") or args.get("title") or "").strip()[:_MAX_TEXT],
        location=(args.get("location") or "").strip()[:_MAX_TEXT],
        work_mode=args.get("work_mode") if args.get("work_mode") in WORK_MODES else "",
        sort=args.get("sort") if args.get("sort") in SORTS else "freshness",
        posted_within=int(posted) if posted.isdigit() and int(posted) in dict(POSTED_WITHIN_OPTIONS) else 0,
        page=_positive_int(args.get("page"), 1),
        page_size=_positive_int(args.get("page_size"), DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE),
    )


def list_query_string(q: ListQuery, **changes) -> str:
    """The canonical query string for q (defaults left out), e.g. "q=sre&page=2"."""
    q = replace(q, **changes)
    defaults = ListQuery()
    pairs = [(k, getattr(q, k)) for k in _PARAMS if getattr(q, k) != getattr(defaults, k)]
    return urlencode(pairs)


def safe_back_query(raw) -> str:
    """A job page's ?back= value, re-parsed so only list parameters come through: it can
    only ever point back at /jobs, never anywhere else."""
    parsed = parse_qs(raw or "", keep_blank_values=False)
    return list_query_string(parse_list_args({k: v[0] for k, v in parsed.items()}))


@dataclass(frozen=True)
class ListResult:
    rows: list
    total: int
    page: int
    total_pages: int
    companies: int     # distinct companies among all matches, not just this page
    locations: int
    new_today: int     # first seen by JobsHub in the last 24 hours


def query_jobs(conn, q: ListQuery, now=None) -> ListResult:
    """One page of jobs for q plus stats over every match; page is clamped to the last page."""
    now = now or datetime.now(timezone.utc)
    where = "WHERE 1=1"
    params: list = []
    if q.q:
        where += " AND (title LIKE ? OR company_name LIKE ?)"
        params += [f"%{q.q}%", f"%{q.q}%"]
    if q.location:
        where += " AND location LIKE ?"
        params.append(f"%{q.location}%")
    if q.work_mode:
        where += " AND is_remote = ?"
        params.append(WORK_MODES[q.work_mode])
    if q.posted_within:
        where += f" AND {POSTED_OR_SEEN} >= ?"
        params.append((now - timedelta(days=q.posted_within)).isoformat())

    total, companies, locations, new_today = conn.execute(
        f"""SELECT COUNT(*), COUNT(DISTINCT company_name), COUNT(DISTINCT location),
                   COALESCE(SUM(first_seen_at >= ?), 0)
            FROM jobs {where}""",
        [(now - NEW_WINDOW).isoformat(), *params],
    ).fetchone()
    total_pages = max(1, (total + q.page_size - 1) // q.page_size)
    page = min(q.page, total_pages)
    rows = conn.execute(
        f"SELECT * FROM jobs {where} ORDER BY {SORTS[q.sort]} LIMIT ? OFFSET ?",
        [*params, q.page_size, (page - 1) * q.page_size],
    ).fetchall()
    return ListResult(rows, total, page, total_pages, companies, locations, new_today)


# ---- site-wide figures for the hero and the location suggestions (cached per process) ----

_SITE_CACHE_SECONDS = 3600
_site_cache: dict = {}


def site_figures(conn):
    """{"total": all jobs, "top_locations": the 20 commonest locations}, refreshed hourly --
    the pipeline only changes the data every few hours."""
    cached = _site_cache.get("value")
    if cached and time.monotonic() - _site_cache["at"] < _SITE_CACHE_SECONDS:
        return cached
    value = {
        "total": conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
        "top_locations": [r[0] for r in conn.execute(
            "SELECT location FROM jobs WHERE location IS NOT NULL AND location != '' "
            "GROUP BY location ORDER BY COUNT(*) DESC LIMIT 20")],
    }
    _site_cache.update(value=value, at=time.monotonic())
    return value


# ---- how one job is shown (list rows, the PC pane, the job page) ----

MONOGRAM_COLOURS = 6  # .mono-0 .. .mono-5 in frontend/src/styles.css
_COMPANY_SUFFIXES = {"inc", "ltd", "llc", "llp", "pvt", "private", "limited", "corp", "corporation",
                     "co", "the", "plc", "gmbh", "sa", "ag", "pte", "technologies", "solutions"}
_CURRENCY = {"USD": "$", "INR": "₹", "EUR": "€", "GBP": "£", "CAD": "CA$", "AUD": "A$", "SGD": "S$"}
_INTERVAL = {"yearly": "yr", "year": "yr", "annual": "yr", "monthly": "mo", "month": "mo",
             "weekly": "wk", "week": "wk", "daily": "day", "day": "day", "hourly": "hr", "hour": "hr"}
_EMPLOYMENT = {"fulltime": "Full-time", "parttime": "Part-time", "contract": "Contract",
               "contractor": "Contract", "internship": "Internship", "intern": "Internship",
               "temporary": "Temporary", "temp": "Temporary", "freelance": "Freelance"}


def monogram(company):
    """("NV", "mono-3"): up to two initials and a stable colour class for a company."""
    words = [w for w in re.findall(r"[A-Za-z0-9]+", company or "") if w.lower() not in _COMPANY_SUFFIXES]
    if not words:
        initials = "?"
    elif len(words) == 1:
        initials = words[0][:2]
    else:
        initials = words[0][0] + words[1][0]
    colour = int(hashlib.sha1((company or "").lower().encode()).hexdigest(), 16) % MONOGRAM_COLOURS
    return initials.upper(), f"mono-{colour}"


def _amount(value, currency):
    if currency == "INR":
        if value >= 1e7:
            return f"{value / 1e7:.3g}Cr"
        if value >= 1e5:
            return f"{value / 1e5:.3g}L"
    if value >= 1e6:
        return f"{value / 1e6:.3g}M"
    if value >= 1e3:
        return f"{value / 1e3:.3g}k"
    return f"{value:.0f}"


def salary_label(compensation):
    """"$125k–160k / yr" from EverJobs' compensation object, or None if it has no amount."""
    if not isinstance(compensation, dict):
        return None
    try:
        low = float(compensation["minAmount"]) if compensation.get("minAmount") else None
        high = float(compensation["maxAmount"]) if compensation.get("maxAmount") else None
    except (TypeError, ValueError):
        return None
    if not low and not high:
        return None
    code = str(compensation.get("currency") or "").upper()
    symbol = _CURRENCY.get(code, f"{code} " if code else "")
    if low and high and low != high:
        amount = f"{symbol}{_amount(low, code)}–{_amount(high, code)}"
    elif low and high:
        amount = f"{symbol}{_amount(low, code)}"
    else:
        amount = f"{'from' if low else 'up to'} {symbol}{_amount(low or high, code)}"
    interval = _INTERVAL.get(str(compensation.get("interval") or "").lower())
    return f"{amount} / {interval}" if interval else amount


def employment_label(value):
    """"Full-time" from Full-Time / FULL_TIME / fulltime / ["Full-time"]; None for anything
    else -- sources put free text here too (e.g. "EOR Mexico"), which isn't a job type."""
    if isinstance(value, list):
        value = value[0] if value else None
    if not value or not isinstance(value, str):
        return None
    key = re.sub(r"[^a-z]", "", value.lower())
    return _EMPLOYMENT.get(key)


def present_job(row, now=None):
    """What the templates show for one jobs row. Only fields the data really has."""
    now = now or datetime.now(timezone.utc)
    try:
        raw = json.loads(row["raw_json"] or "{}")
    except ValueError:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    initials, colour = monogram(row["company_name"])
    try:
        seen = datetime.fromisoformat((row["first_seen_at"] or "").replace("Z", "+00:00"))
        is_new = now - (seen if seen.tzinfo else seen.replace(tzinfo=timezone.utc)) < NEW_WINDOW
    except ValueError:
        is_new = False
    department = raw.get("department") or raw.get("team")
    return {
        "id": row["id"],
        "title": row["title"],
        "company": row["company_name"] or "",
        "location": row["location"] or "",
        "posted": posted_label(row["posted_at"], row["first_seen_at"], now),
        "posted_on": (row["posted_at"] or row["first_seen_at"] or "")[:10],
        "is_remote": bool(row["is_remote"]),
        "is_new": is_new,
        "employment": employment_label(row["employment_type"] or raw.get("employmentType") or raw.get("jobType")),
        "department": department.strip()[:40] if isinstance(department, str) and department.strip() else None,
        "salary": salary_label(raw.get("compensation")),
        "monogram": initials,
        "monogram_class": colour,
    }


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
