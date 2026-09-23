import re

from jobhub_poc.webapp.app import create_app


def _html(conn, path):
    app = create_app(test_conn=conn)
    app.config["TESTING"] = True
    return app.test_client().get(path).get_data(as_text=True)


def test_static_urls_carry_a_content_version(conn):
    """Cloudflare overrides the origin's Cache-Control and tells browsers to keep
    /static/* for 4 hours, so an unversioned URL keeps serving a stale auth.js after a
    deploy (2026-09-23: a pre-Turnstile auth.js sent no token, every signup got 403)."""
    html = _html(conn, "/register")
    assert re.search(r'/static/auth\.js\?v=[0-9a-f]{12}"', html)
    assert re.search(r'/static/style\.css\?v=[0-9a-f]{12}"', html)


def test_version_changes_when_the_file_changes(conn, tmp_path, monkeypatch):
    app = create_app(test_conn=conn)
    static = tmp_path / "static"
    static.mkdir()
    (static / "auth.js").write_text("one")
    monkeypatch.setattr(app, "static_folder", str(static))
    with app.test_request_context():
        from flask import url_for
        first = url_for("static", filename="auth.js")
        (static / "auth.js").write_text("two")
        second = url_for("static", filename="auth.js")
    assert first != second


def test_missing_static_file_still_builds_a_url(conn):
    app = create_app(test_conn=conn)
    with app.test_request_context():
        from flask import url_for
        assert url_for("static", filename="nope.js") == "/static/nope.js"
