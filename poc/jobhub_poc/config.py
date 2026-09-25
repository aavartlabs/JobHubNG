import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

_ENV_FILE = os.environ.get("JOBHUB_POC_ENV_FILE")
if _ENV_FILE:
    load_dotenv(_ENV_FILE)
else:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")


SQLITE_PATH = os.environ.get("JOBHUB_SQLITE_PATH", "./data/jobhub.db")

WEB_PORT = int(os.environ.get("WEB_PORT", "8100"))
WEB_SECRET_KEY = os.environ.get("WEB_SECRET_KEY", "dev-only-change-me")

NOTIFIER_BACKEND = os.environ.get("NOTIFIER_BACKEND", "console")
WHATSAPP_GATEWAY_URL = os.environ.get("WHATSAPP_GATEWAY_URL", "")
WHATSAPP_GATEWAY_API_KEY = os.environ.get("WHATSAPP_GATEWAY_API_KEY", "")
# Where admin-only messages go -- ops alerts when a backup, restore drill or cold export
# fails, and admin sign-in codes (admin_notify.py). Telegram first when set, WhatsApp as the
# fallback. Admin only -- never a site user's chat or number.
# ADMIN_TELEGRAM_CHAT_ID is the admin's chat with the bot (the bot's reply to /start
# shows it). Everything Telegram goes through poc/telegram-gateway/, which alone holds the
# bot token.
ADMIN_TELEGRAM_CHAT_ID = os.environ.get("ADMIN_TELEGRAM_CHAT_ID", "")
# The shared .env's value is for the host (alert CLIs: http://127.0.0.1:3300); compose
# overrides it for the web container.
TELEGRAM_GATEWAY_URL = os.environ.get("TELEGRAM_GATEWAY_URL", "")
TELEGRAM_GATEWAY_API_KEY = os.environ.get("TELEGRAM_GATEWAY_API_KEY", "")
# The fallback admin number (E.164, e.g. +91...).
ADMIN_ALERT_WHATSAPP = os.environ.get("ADMIN_ALERT_WHATSAPP", "")
# Resend, for alert digests sent by email (alerts/senders.py). The same Resend account as
# auth-service's OTP emails; RESEND_FROM_EMAIL must be on a Resend-verified domain.
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "")

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

# AI (jobhub_poc/ai/). AI_BACKEND picks the writing models: "ollama" (default: a local model
# on the LAN, OLLAMA_URL / OLLAMA_MODEL; resumes stay on JobsHub's machines) or "openrouter"
# (hosted: ai/openrouter.py, "write" tasks only to models that don't train on resume data,
# "jobs" tasks may use AI_MODELS_JOBS incl. direct:meta). Jev (TypeSafe) makes judgments --
# job reading, matching -- when TYPESAFE_API_KEY is set. Unset/unreachable = "AI offline":
# tasks wait, and matching falls back to plain word matching.
# AI_PAUSED=1 makes no AI calls at all (paid services off until needed); AI_READ_ALL_JOBS=1
# reads every listed job in the background after each pipeline load (ai/queue_reads.py).
AI_BACKEND = os.environ.get("AI_BACKEND", "ollama")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e2b")
# Context window asked for on every request (tokens); unset = the Ollama server's own setting.
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX") or 0)
AI_PAUSED = os.environ.get("AI_PAUSED", "") == "1"
AI_READ_ALL_JOBS = os.environ.get("AI_READ_ALL_JOBS", "") == "1"
TYPESAFE_API_KEY = os.environ.get("TYPESAFE_API_KEY", "")
TYPESAFE_MODEL = os.environ.get("TYPESAFE_MODEL", "jev-latest")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
AI_MODELS_WRITE = [m.strip() for m in os.environ.get(
    "AI_MODELS_WRITE", "openai/gpt-6-luna-pro,deepseek/deepseek-v4-flash").split(",") if m.strip()]
AI_MODELS_JOBS = [m.strip() for m in os.environ.get(
    "AI_MODELS_JOBS", "openai/gpt-6-luna-pro,deepseek/deepseek-v4-flash").split(",") if m.strip()]
OPENROUTER_ZDR = os.environ.get("OPENROUTER_ZDR", "") == "1"  # only zero-data-retention endpoints for resume data
OPENROUTER_STRICT = os.environ.get("OPENROUTER_STRICT", "") == "1"  # strict schema (needs strict-compatible schemas)
AI_MAX_TOKENS = int(os.environ.get("AI_MAX_TOKENS", "4096"))
# How hard reasoning models think before answering (sent only to models that take it):
# "low" keeps judgments and rewrites quick; the honesty checks run on the answer either way.
AI_REASONING_EFFORT = os.environ.get("AI_REASONING_EFFORT", "low")
# How many AI tasks run at once (ai/worker.py): one local GPU does one at a time; hosted
# models take many requests in parallel (a job list queues ~25 reads).
AI_WORKERS = int(os.environ.get("AI_WORKERS") or (1 if AI_BACKEND == "ollama" else 6))
# When OpenRouter is down, public job text may go straight to these (ai/direct.py; each needs
# <NAME>_API_KEY / _BASE_URL / _MODEL in .env). Never resume data.
DIRECT_JOBS_PROVIDERS = [p.strip() for p in os.environ.get("DIRECT_JOBS_PROVIDERS", "deepseek").split(",") if p.strip()]
# Resume consent given before this ISO time no longer counts (resume_consent.py): set it to
# the moment AI_BACKEND changes. Unset = the backend's own date.
RESUME_CONSENT_SINCE = os.environ.get("RESUME_CONSENT_SINCE", "")
# Fernet key (base64) that encrypts uploaded resumes and everything derived from them
# (crypto.py). Unset = resume upload is switched off. Keep a copy offline: without it the
# encrypted rows in jobhub.db and its backups can't be read.
RESUME_ENCRYPTION_KEY = os.environ.get("RESUME_ENCRYPTION_KEY", "")
# PDFs with embedded fonts/images are often 2-5 MB; 2 MB turned real resumes away.
MAX_RESUME_BYTES = 5 * 1024 * 1024

# "Popular" search chips under the jobs page's search bar: a curated, comma-separated list
# (not derived from users' alert terms, which are private). Each searches title/company,
# so they should be role or company words, not places.
POPULAR_SEARCHES = [
    term.strip() for term in os.environ.get(
        "POPULAR_SEARCHES",
        "SRE, DevOps, Data Engineer, Product Manager, Solutions Architect, Designer, Sales, Analyst",
    ).split(",") if term.strip()
]


# Former public hostnames of this deployment (comma-separated). Requests for them are
# permanently redirected to the same path on WEB_ORIGIN (webapp/app.py), so old links --
# bookmarks, digests already sent -- keep working. The tunnel must still route them here.
LEGACY_HOSTS = {h.strip().lower() for h in os.environ.get("LEGACY_HOSTS", "").split(",") if h.strip()}


def hostnames_from_origin(origin):
    return {urlparse(origin).hostname} if urlparse(origin).hostname else set()


# Cloudflare Turnstile (webapp/turnstile.py). The sitekey is public; the secret is not.
# Get both from the Turnstile widget in the Cloudflare dashboard. For local dev without a
# real widget, Cloudflare's published test pair (sitekey 1x00000000000000000000AA, secret
# 1x0000000000000000000000000000000AA) works only with TURNSTILE_ALLOW_TEST_KEYS=1.
TURNSTILE_SITEKEY = os.environ.get("TURNSTILE_SITEKEY", "")
CF_TURNSTILE_SECRET = os.environ.get("CF_TURNSTILE_SECRET", "")
# Hostnames a token must have been solved on. Defaults to WEB_ORIGIN's host, so a
# production deployment never accepts a token solved on localhost.
TURNSTILE_HOSTNAMES = {
    h.strip() for h in os.environ.get("TURNSTILE_HOSTNAMES", "").split(",") if h.strip()
} or hostnames_from_origin(WEB_ORIGIN)
TURNSTILE_ALLOW_TEST_KEYS = os.environ.get("TURNSTILE_ALLOW_TEST_KEYS", "") == "1"

# Shared key for auth-service's /internal/admin/* API (auth-service/src/admin.js), which
# the admin pages use to list/edit/delete users. docker-compose.yml passes this same value
# to auth-service as ADMIN_API_KEY. Empty disables the admin user pages.
AUTH_ADMIN_API_KEY = os.environ.get("AUTH_ADMIN_API_KEY", "")

# Admin login brute-force lockout (webapp/admin.py): after ADMIN_MAX_FAILURES failed
# attempts from one IP or against one username, lock that key for ADMIN_LOCKOUT_MINUTES,
# doubling on each further lockout, capped at ADMIN_LOCKOUT_MAX_MINUTES.
ADMIN_MAX_FAILURES = int(os.environ.get("ADMIN_MAX_FAILURES", "5"))
ADMIN_LOCKOUT_MINUTES = int(os.environ.get("ADMIN_LOCKOUT_MINUTES", "15"))
ADMIN_LOCKOUT_MAX_MINUTES = int(os.environ.get("ADMIN_LOCKOUT_MAX_MINUTES", str(24 * 60)))
