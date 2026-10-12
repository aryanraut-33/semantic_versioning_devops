"""Small Flask API used to demonstrate controlled software releases."""

import os
from pathlib import Path

from flask import Flask, jsonify


def create_app() -> Flask:
    """Create the API and load release information once at startup."""
    app = Flask(__name__)
    version_file = Path(__file__).resolve().with_name("VERSION")
    app.config["APP_VERSION"] = version_file.read_text(encoding="utf-8").strip()
    app.config["APP_COMMIT"] = os.environ.get("APP_COMMIT", "").strip() or "unknown"

    if not app.config["APP_VERSION"]:
        raise ValueError("VERSION must contain the application version.")

    @app.get("/")
    def index():
        return jsonify(message="Hi, I am Aryan...This is my DEVOPS project")

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.get("/version")
    def version():
        return jsonify(
            version=app.config["APP_VERSION"],
            commit=app.config["APP_COMMIT"],
        )

    return app
