"""Job-board APIs fetched at ingest, next to the EverJobs sweep: official APIs, so they aren't
blocked the way Naukri, Indeed and Glassdoor block EverJobs' scrapers -- which leaves the
sweep with company career pages, mostly US/EU. These cover India ([sources] in
config/pipeline.ini).

Each result is mapped to EverJobs' job shape, so the warehouse treats it like any other: same
id or same title + company + city is one job (a company-page posting found here too merges),
and the posted-date filter applies. Both APIs return only a short description (Adzuna up to
500 characters, Careerjet a ~170-character snippet); the link opens the full posting.

EverJobs has connectors for these too, but they don't work (2026-09-26: Careerjet over https,
which the API refuses; Jooble HTTP 400; Adzuna an empty error), hence this module.

Never fatal: a source whose key is missing, rejected or out of quota is skipped for the run
and reported in the stats.
"""
import hashlib
import os
import time
from datetime import timezone
from email.utils import parsedate_to_datetime

import requests

USER_AGENT = "JobsHub/1.0 (+https://jobshub.aavartlabs.com)"
# Careerjet's API requires a Referer naming the page that shows its results.
REFERER = "https://jobshub.aavartlabs.com/jobs"
ADZUNA_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/1"
# Careerjet's (legacy) public API answers on http only; https connections are refused.
CAREERJET_URL = "http://public.api.careerjet.net/search"


class QuotaOrKey(RuntimeError):
    """The source won't answer this run (key rejected, quota used up): stop asking it."""


def _remote(*texts):
    return any("remote" in (t or "").lower() for t in texts)


def adzuna(query, cfg, session, env):
    resp = session.get(ADZUNA_URL.format(country=cfg.adzuna_country), timeout=30, params={
        "app_id": env["ADZUNA_APP_ID"], "app_key": env["ADZUNA_APP_KEY"], "what": query,
        "results_per_page": 50, "sort_by": "date", "content-type": "application/json"})
    if resp.status_code in (401, 403, 429):
        raise QuotaOrKey(f"adzuna: HTTP {resp.status_code}")
    resp.raise_for_status()
    jobs = []
    for r in resp.json().get("results") or []:
        # [country, state, city, locality...]: e.g. India, Karnataka, Bangalore, Richmond Town.
        area = (r.get("location") or {}).get("area") or []
        jobs.append({
            "id": f"adzuna-{r.get('id')}", "site": "adzuna",
            "title": r.get("title") or "", "companyName": (r.get("company") or {}).get("display_name"),
            "location": {"country": area[0] if area else None, "state": area[1] if len(area) > 1 else None,
                         "city": area[2] if len(area) > 2 else None},
            "description": r.get("description"), "jobUrl": r.get("redirect_url"), "applyUrl": r.get("redirect_url"),
            "datePosted": r.get("created"), "employmentType": r.get("contract_time"),
            "isRemote": _remote(r.get("title"), (r.get("location") or {}).get("display_name")),
        })
    return jobs


def _careerjet_date(value):
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def careerjet(query, cfg, session, env):
    resp = session.get(CAREERJET_URL, timeout=30, headers={"User-Agent": USER_AGENT, "Referer": REFERER}, params={
        "locale_code": cfg.careerjet_locale, "keywords": query, "location": cfg.careerjet_location,
        "affid": env["CAREERJET_AFFID"], "user_ip": env["CAREERJET_USER_IP"], "user_agent": USER_AGENT,
        "pagesize": 99, "sort": "date"})
    resp.raise_for_status()
    data = resp.json()
    if data.get("type") == "ERROR":
        raise QuotaOrKey(f"careerjet: {str(data.get('error'))[:120]}")
    jobs = []
    for r in data.get("jobs") or []:
        url = r.get("url") or ""
        parts = [p.strip() for p in (r.get("locations") or "").split(",") if p.strip()]
        jobs.append({
            # Careerjet gives no id; its link is stable per posting.
            "id": "careerjet-" + hashlib.sha1(url.encode()).hexdigest()[:16], "site": "careerjet",
            "title": r.get("title") or "", "companyName": r.get("company") or None,
            "location": {"city": parts[0] if parts else None, "state": parts[1] if len(parts) > 1 else None,
                         "country": cfg.careerjet_location},
            "description": r.get("description"), "jobUrl": url, "applyUrl": url,
            "datePosted": _careerjet_date(r.get("date")), "isRemote": _remote(r.get("title"), r.get("locations")),
        })
    return jobs


SOURCES = {"adzuna": (adzuna, ("ADZUNA_APP_ID", "ADZUNA_APP_KEY"), "adzuna_requests_per_run"),
           "careerjet": (careerjet, ("CAREERJET_AFFID",), "careerjet_requests_per_run")}


def public_ip(session):
    """Careerjet wants the searching user's IP; for a batch fetch that's this server's."""
    try:
        return session.get("https://api.ipify.org", timeout=10).text.strip()
    except requests.RequestException:
        return ""


def fetch_all(cfg, env=None, session=None, sleep=time.sleep):
    """(jobs, stats) from every source in cfg.enabled. cfg: pipeline_config.SourcesConfig."""
    env = dict(os.environ if env is None else env)
    session = session or requests.Session()
    jobs, stats = [], {}
    for name in cfg.enabled:
        if name not in SOURCES:
            stats[name] = {"skipped": "unknown source"}
            continue
        fetch, keys, cap_field = SOURCES[name]
        missing = [k for k in keys if not env.get(k)]
        if missing:
            stats[name] = {"skipped": f"missing {', '.join(missing)} in scraper/.env"}
            continue
        if name == "careerjet" and not env.get("CAREERJET_USER_IP"):
            env["CAREERJET_USER_IP"] = public_ip(session)
        s = stats[name] = {"requests": 0, "jobs": 0, "errors": 0}
        for i, query in enumerate(cfg.queries[:getattr(cfg, cap_field)]):
            if i and cfg.delay_ms:
                sleep(cfg.delay_ms / 1000)
            s["requests"] += 1
            try:
                found = fetch(query, cfg, session, env)
            except QuotaOrKey as exc:
                s["stopped"] = str(exc)
                break
            except (requests.RequestException, ValueError) as exc:  # one query failing isn't the source failing
                s["errors"] += 1
                s["last_error"] = f"{type(exc).__name__}"[:80]
                continue
            s["jobs"] += len(found)
            jobs += found
    return jobs, stats
