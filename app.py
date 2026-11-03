"""Fitness calculator used to demonstrate controlled software releases."""

import os
import socket
from pathlib import Path

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from fitness import ACTIVITIES, InputError, estimate


def create_app() -> Flask:
    """Create the API and load release information once at startup."""
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
    version_file = Path(__file__).resolve().with_name("VERSION")
    app.config["APP_VERSION"] = version_file.read_text(encoding="utf-8").strip()
    app.config["APP_COMMIT"] = os.environ.get("APP_COMMIT", "").strip() or "unknown"
    app.config["INSTANCE_ID"] = os.environ.get("INSTANCE_ID", "").strip() or socket.gethostname()

    @app.after_request
    def identify_instance(response):
        response.headers["X-Instance-ID"] = app.config["INSTANCE_ID"]
        return response

    if not app.config["APP_VERSION"]:
        raise ValueError("VERSION must contain the application version.")

    @app.errorhandler(HTTPException)
    def http_error(error):
        if request.path.startswith("/api/"):
            response = error.get_response()
            response.data = app.json.dumps({"error": error.description})
            response.content_type = "application/json"
            return response
        return error

    @app.get("/api/activities")
    def activities():
        return jsonify(activities=[
            {"id": key, "label": label, "factor": factor}
            for key, (label, factor) in ACTIVITIES.items()
        ])

    def fitness_response(kind):
        data = request.get_json()
        try:
            return jsonify(estimate(data, kind))
        except InputError as error:
            return jsonify(error=str(error), field=error.field), 400

    @app.post("/api/fitness")
    def fitness():
        return fitness_response("fitness")

    @app.post("/api/calories")
    def calories():
        return fitness_response("calories")

    @app.post("/api/bmi")
    def bmi():
        return fitness_response("bmi")

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
