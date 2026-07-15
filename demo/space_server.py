"""Serve the built Demo App and its existing API from one WSGI app."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, send_from_directory
from werkzeug.utils import safe_join

from demo.api_server import app as api_app


DIST_DIR = Path(__file__).resolve().parent.parent / "demo-app" / "dist"
app = Flask(__name__, static_folder=None)


class _ApiPathDispatcher:
    def __init__(self, frontend_wsgi_app, api_wsgi_app):
        self.frontend_wsgi_app = frontend_wsgi_app
        self.api_wsgi_app = api_wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        is_api_path = path == "/api" or path.startswith("/api/")
        wsgi_app = self.api_wsgi_app if is_api_path else self.frontend_wsgi_app
        return wsgi_app(environ, start_response)


@app.get("/")
def space_index():
    return send_from_directory(DIST_DIR, "index.html")


@app.get("/<path:frontend_path>")
def space_frontend(frontend_path: str):
    requested = safe_join(DIST_DIR, frontend_path)
    if requested is not None and Path(requested).is_file():
        return send_from_directory(DIST_DIR, frontend_path)
    return send_from_directory(DIST_DIR, "index.html")


app.wsgi_app = _ApiPathDispatcher(app.wsgi_app, api_app.wsgi_app)
