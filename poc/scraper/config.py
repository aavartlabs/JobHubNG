import os

from dotenv import load_dotenv

load_dotenv(os.environ.get("JOBHUB_POC_SCRAPER_ENV_FILE", ".env"))

EVER_JOBS_API_URL = os.environ.get("EVER_JOBS_API_URL", "http://localhost:3001")
EVER_JOBS_API_KEY = os.environ.get("EVER_JOBS_API_KEY") or None
EVER_JOBS_SITE_NAMES = os.environ.get("EVER_JOBS_SITE_NAMES", "google")
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("REQUEST_TIMEOUT_SECONDS", "240"))

SEARCH_TERMS = [t.strip() for t in os.environ.get(
    "SEARCH_TERMS",
    "engineer,product manager,data analyst,data scientist,designer,marketing,sales,"
    "customer success,operations,finance,human resources,devops,quality assurance,"
    "content,recruiter",
).split(",") if t.strip()]
RESULTS_PER_TERM = int(os.environ.get("RESULTS_PER_TERM", "50"))
DUMP_DIR = os.environ.get("DUMP_DIR", "./dumps")
