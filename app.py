"""Arithmetic calculator used to demonstrate controlled software releases."""

import math
import operator
import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request


OPERATIONS = {
    "add": (operator.add, "+"),
    "subtract": (operator.sub, "-"),
    "multiply": (operator.mul, "×"),
    "divide": (operator.truediv, "÷"),
}


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
        return render_template("calculator.html", a="", b="", result=None, error=None)

    def calculation_response(operation, a, b, result=None, error=None):
        status = 400 if error else 200
        if request.args.get("format") == "html":
            return render_template(
                "calculator.html",
                a=a,
                b=b,
                result=result,
                error=error,
                symbol=OPERATIONS[operation][1],
            ), status
        if error:
            return jsonify(error=error), status
        return jsonify(operation=operation, a=a, b=b, result=result), status

    def calculate(operation):
        raw_a = request.args.get("a", "")
        raw_b = request.args.get("b", "")

        def invalid(message):
            return calculation_response(operation, raw_a, raw_b, error=message)

        if len(request.args.getlist("a")) != 1 or len(request.args.getlist("b")) != 1:
            return invalid("Provide exactly one value for both a and b.")
        try:
            a, b = float(raw_a), float(raw_b)
        except ValueError:
            return invalid("a and b must be valid numbers.")
        if not math.isfinite(a) or not math.isfinite(b):
            return invalid("a and b must be finite numbers.")
        if operation == "divide" and b == 0:
            return invalid("Cannot divide by zero.")

        result = OPERATIONS[operation][0](a, b)
        if not math.isfinite(result):
            return invalid("Result is outside the supported numeric range.")
        return calculation_response(operation, a, b, result=result)

    @app.get("/add")
    def add():
        return calculate("add")

    @app.get("/subtract")
    def subtract():
        return calculate("subtract")

    @app.get("/multiply")
    def multiply():
        return calculate("multiply")

    @app.get("/divide")
    def divide():
        return calculate("divide")

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
