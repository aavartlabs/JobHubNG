import hashlib
import logging
import os
from datetime import timedelta

from flask import Flask, g, redirect, url_for

from jobhub_poc import config, db
from jobhub_poc.webapp import admin, auth, auth_proxy, routes_alerts, routes_api, routes_jobs


def create_app(test_conn=None):
    app = Flask(__name__)
    app.secret_key = config.WEB_SECRET_KEY
    # INFO, not Flask's default WARNING outside debug: admin.py's audit trail (sign-ins,
    # user edits/deletes) is logged at INFO and must reach `docker logs jobhub-web`.
    app.logger.setLevel(logging.INFO)
    # Flask's own session cookie carries only the admin console login (admin.py); site
    # users' sessions are auth-service's cookie, never this one.
    app.config.update(
        SESSION_COOKIE_NAME="jobhub_admin",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=config.WEB_ORIGIN.startswith("https://"),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    )

    def get_db():
        if test_conn is not None:
            return test_conn
        if "db" not in g:
            g.db = db.get_connection()
            db.init_db(g.db)
        return g.db

    app.get_db = get_db

    @app.teardown_appcontext
    def close_db(exception=None):
        if test_conn is None:
            conn = g.pop("db", None)
            if conn is not None:
                conn.close()

    app.before_request(auth.load_current_user)

    # Cloudflare overrides the origin's Cache-Control and has browsers keep /static/*
    # for 4 hours, so a deploy's new auth.js/app.js/style.css wouldn't reach anyone who
    # visited recently. A content hash in the URL makes every change a new URL.
    static_versions = {}

    @app.url_defaults
    def version_static_urls(endpoint, values):
        if endpoint != "static" or "filename" not in values:
            return
        path = os.path.join(app.static_folder, values["filename"])
        try:
            stat = os.stat(path)
        except OSError:
            return
        key = (path, stat.st_mtime_ns, stat.st_size)
        if key not in static_versions:
            with open(path, "rb") as f:
                static_versions[key] = hashlib.sha256(f.read()).hexdigest()[:12]
        values["v"] = static_versions[key]

    @app.context_processor
    def inject_template_globals():
        return {
            "turnstile_sitekey": config.TURNSTILE_SITEKEY,
            "is_admin": admin.is_admin,
            "csrf_token": admin.csrf_token,
        }

    app.register_blueprint(auth.bp)
    app.register_blueprint(auth_proxy.bp)
    app.register_blueprint(routes_jobs.bp)
    app.register_blueprint(routes_alerts.bp)
    app.register_blueprint(routes_api.bp)
    app.register_blueprint(admin.bp)

    @app.route("/")
    def index():
        return redirect(url_for("jobs.list_jobs"))

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=config.WEB_PORT)
