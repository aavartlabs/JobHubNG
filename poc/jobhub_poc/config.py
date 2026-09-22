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

NOTIFIER_BACKEND = os.environ.get("NOTIFIER_BACKEND", "console")
WHATSAPP_GATEWAY_URL = os.environ.get("WHATSAPP_GATEWAY_URL", "")
WHATSAPP_GATEWAY_API_KEY = os.environ.get("WHATSAPP_GATEWAY_API_KEY", "")

# poc/auth-service/ -- the standalone Better Auth companion service. Reached only
# server-side (auth_proxy.py's passthrough, and auth.py's get-session/sign-out calls),
# never exposed to the host in docker-compose.yml. Port 3200 matches auth-service's own
# PORT default (src/server.js / auth-service/.env.example), not an arbitrary choice --
# don't drift this from that service's actual default without changing both.
AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "http://localhost:3200")
# The origin this Flask app is itself publicly reachable at. auth.py's /logout route
# makes a server-to-server POST {AUTH_SERVICE_URL}/auth/sign-out call that carries the
# session cookie; Better Auth's CSRF check requires such calls to send an Origin header
# matching a value in the auth-service's own TRUSTED_ORIGINS config (poc/auth-service/.env)
# -- see poc/auth-service/README.md's "Cookie-bearing POST requests" note. Browser-driven
# calls through auth_proxy.py already send this same origin automatically and don't need
# this value; it exists only for Flask's own direct server-to-server call.
WEB_ORIGIN = os.environ.get("WEB_ORIGIN", "http://localhost:8100")
