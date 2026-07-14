"""Serve the built Demo App and its existing API from one Flask app."""

from __future__ import annotations

from pathlib import Path

from flask import jsonify, send_from_directory

from demo.api_server import app


DIST_DIR = Path(__file__).resolve().parent.parent / "demo-app" / "dist"


@app.get("/")
def space_index():
    return send_from_directory(DIST_DIR, "index.html")


@app.get("/<path:frontend_path>")
def space_frontend(frontend_path: str):
    if frontend_path.startswith("api/"):
        return jsonify({"message": "API route not found."}), 404
    requested = DIST_DIR / frontend_path
    if requested.is_file():
        return send_from_directory(DIST_DIR, frontend_path)
    return send_from_directory(DIST_DIR, "index.html")
