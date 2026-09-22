import os

from dotenv import load_dotenv

load_dotenv(os.environ.get("JOBHUB_POC_SCRAPER_ENV_FILE", ".env"))

EVER_JOBS_API_URL = os.environ.get("EVER_JOBS_API_URL", "http://localhost:3001")
EVER_JOBS_API_KEY = os.environ.get("EVER_JOBS_API_KEY") or None
# Informational only (logged in dump_jobs.py) -- the actual site bucket(s) scraped are
# controlled server-side by EverJobs' own DEFAULT_SITE_NAMES env var, not by anything this
# client sends per-request. Keep this in sync with the live value so the log is accurate.
EVER_JOBS_SITE_NAMES = os.environ.get("EVER_JOBS_SITE_NAMES", "google,naukri,linkedin,indeed,glassdoor")
# Raised from 240s: widened from 1 to 5 site buckets on 2026-09-22 (server-side config, see
# EVER_JOBS_SITE_NAMES above); confirmed live that 1-2 buckets combined cost roughly the same
# (~80MB, ~2m38s) as a single bucket, not additive, but 5 buckets was never directly timed --
# this margin absorbs that residual uncertainty rather than risk a live pipeline timeout.
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("REQUEST_TIMEOUT_SECONDS", "600"))

SEARCH_TERMS = [t.strip() for t in os.environ.get(
    "SEARCH_TERMS",
    "engineer,product manager,data analyst,data scientist,designer,marketing,sales,"
    "customer success,operations,finance,human resources,devops,quality assurance,"
    "content,recruiter,manager,analyst,consultant,intern,director",
).split(",") if t.strip()]
RESULTS_PER_TERM = int(os.environ.get("RESULTS_PER_TERM", "100"))
DUMP_DIR = os.environ.get("DUMP_DIR", "./dumps")
