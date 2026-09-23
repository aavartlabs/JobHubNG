"""Client for auth-service's internal user API (auth-service/src/admin.js), shared by the
admin console (webapp/admin.py) and the alert pipeline (alerts/contacts.py).

The API lives at /internal/admin/users on AUTH_SERVICE_URL: reachable from the web
container over the Docker network, and from the pi09 host (where alerts run) through the
loopback-only port docker-compose publishes. Every call carries AUTH_ADMIN_API_KEY.
"""
import requests

from jobhub_poc import config

_TIMEOUT_SECONDS = 10


class AuthServiceError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def call(method, path="", json=None):
    if not config.AUTH_ADMIN_API_KEY:
        raise AuthServiceError("AUTH_ADMIN_API_KEY is not set, so the admin API is disabled", 503)
    try:
        resp = requests.request(
            method,
            f"{config.AUTH_SERVICE_URL}/internal/admin/users{path}",
            headers={"x-admin-api-key": config.AUTH_ADMIN_API_KEY},
            json=json,
            timeout=_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise AuthServiceError(f"auth-service unreachable: {exc}") from exc
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if not resp.ok:
        raise AuthServiceError(data.get("error") or f"auth-service returned {resp.status_code}", resp.status_code)
    return data
