"""Job links people can open. Stdlib only: pi05's scraper imports this too.

EverJobs gives SmartRecruiters jobs their *API* URL as the link
(https://api.smartrecruiters.com/v1/companies/<company>/postings/<id>), which shows a page
of JSON. The posting's own page is https://jobs.smartrecruiters.com/<company>/<id> (the
usual "-<title-slug>" suffix is optional)."""
import re

_SMARTRECRUITERS_API = re.compile(
    r"^https?://api\.smartrecruiters\.com/v1/companies/([^/?#]+)/postings/([^/?#]+)/?(?:[?#].*)?$", re.I)


def smartrecruiters_api(url):
    """(company, posting id) if `url` is a SmartRecruiters Posting API URL, else None."""
    m = _SMARTRECRUITERS_API.match((url or "").strip()) if isinstance(url, str) else None
    return (m.group(1), m.group(2)) if m else None


def human_url(url):
    """The page a person should open for `url` (unchanged unless it's a known API URL)."""
    parts = smartrecruiters_api(url)
    if parts:
        return f"https://jobs.smartrecruiters.com/{parts[0]}/{parts[1]}"
    return url
