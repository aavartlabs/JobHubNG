"""POST /telegram/webhook: Telegram's updates for the bot, passed through unchanged to
poc/telegram-gateway (which checks the X-Telegram-Bot-Api-Secret-Token header and does
the handling). It's here only because the Cloudflare Tunnel reaches jobhub-web alone.
A non-2xx answer makes Telegram redeliver the update later, which is what we want if the
gateway is down."""
import requests
from flask import Blueprint, Response, jsonify, request

from jobhub_poc import config

bp = Blueprint("telegram_webhook", __name__)

SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"
_MAX_BODY_BYTES = 64 * 1024
_TIMEOUT_SECONDS = 30


@bp.route("/telegram/webhook", methods=["POST"])
def webhook():
    if not config.TELEGRAM_GATEWAY_URL:
        return jsonify(error="telegram is not configured"), 503
    if (request.content_length or 0) > _MAX_BODY_BYTES:
        return jsonify(error="too large"), 413
    try:
        upstream = requests.post(
            f"{config.TELEGRAM_GATEWAY_URL.rstrip('/')}/webhook",
            data=request.get_data(cache=False)[:_MAX_BODY_BYTES],
            headers={"Content-Type": "application/json", SECRET_HEADER: request.headers.get(SECRET_HEADER, "")},
            timeout=_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        return jsonify(error="telegram gateway unreachable"), 502
    return Response(upstream.content, status=upstream.status_code, content_type="application/json")
