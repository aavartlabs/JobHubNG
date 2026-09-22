"""Byte-level passthrough for everything under /auth/* to poc/auth-service/'s own
Better Auth router. Exists because the browser only ever talks to this Flask app on one
public origin -- the auth-service itself is never exposed to the host (see
docker-compose.yml) -- and because Better Auth's CSRF check validates the browser's own
Origin header, which this passthrough forwards unchanged rather than reconstructing.

This does not parse or reshape request/response bodies at all: Better Auth speaks JSON,
this just relays whatever bytes came in and whatever bytes come back, including
Set-Cookie (so sign-in/sign-up/sign-out cookies reach the browser as if talking to
Better Auth directly).
"""
import requests
from flask import Blueprint, Response, jsonify, request

from jobhub_poc import config

bp = Blueprint("auth_proxy", __name__)

# Headers that are specific to a single hop and must not be relayed verbatim in either
# direction (RFC 2616 sec. 13.5.1's hop-by-hop set, plus Content-Length/Content-Encoding
# since the relayed body's actual length/encoding can differ from the original -- Flask
# and `requests` each recompute these correctly on their own).
_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-encoding",
    "content-length",
}
_PROXY_TIMEOUT_SECONDS = 10


@bp.route("/auth/<path:subpath>", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
def proxy(subpath):
    outbound_headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in _HOP_BY_HOP_HEADERS and key.lower() != "host"
    }

    try:
        upstream = requests.request(
            method=request.method,
            url=f"{config.AUTH_SERVICE_URL}/auth/{subpath}",
            headers=outbound_headers,
            params=request.args,
            data=request.get_data(),
            timeout=_PROXY_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        return jsonify({"error": f"auth-service unreachable: {exc}"}), 502

    # upstream.raw.headers (a urllib3 HTTPHeaderDict) preserves repeated header names --
    # unlike upstream.headers, which comma-joins duplicates and would corrupt multiple
    # Set-Cookie headers into one unparseable value.
    response_headers = [
        (key, value)
        for key, value in upstream.raw.headers.items()
        if key.lower() not in _HOP_BY_HOP_HEADERS
    ]
    return Response(upstream.content, status=upstream.status_code, headers=response_headers)
