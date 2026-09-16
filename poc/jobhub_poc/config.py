import os
from pathlib import Path

from dotenv import load_dotenv

_ENV_FILE = os.environ.get("JOBHUB_POC_ENV_FILE")
if _ENV_FILE:
    load_dotenv(_ENV_FILE)
else:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")


SQLITE_PATH = os.environ.get("JOBHUB_SQLITE_PATH", "./data/jobhub.db")
PURGE_WINDOW_DAYS = int(os.environ.get("PURGE_WINDOW_DAYS", "15"))

WEB_PORT = int(os.environ.get("WEB_PORT", "8100"))
WEB_SECRET_KEY = os.environ.get("WEB_SECRET_KEY", "dev-only-change-me")
WEB_ADMIN_USERNAME = os.environ.get("WEB_ADMIN_USERNAME", "admin")
WEB_ADMIN_PASSWORD = os.environ.get("WEB_ADMIN_PASSWORD", "change-me")

NOTIFIER_BACKEND = os.environ.get("NOTIFIER_BACKEND", "console")
WHATSAPP_GATEWAY_URL = os.environ.get("WHATSAPP_GATEWAY_URL", "")
WHATSAPP_GATEWAY_API_KEY = os.environ.get("WHATSAPP_GATEWAY_API_KEY", "")
