"""Verify the packaged API over HTTP using only the Python standard library."""

import argparse
import json
import re
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def check_response(base_url, endpoint, expected, expected_status=200, payload=None):
    """Check required fields while allowing compatible additional fields."""
    try:
        url = f"{base_url.rstrip('/')}{endpoint}"
        target = url if payload is None else Request(
            url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
        )
        response = urlopen(target, timeout=2)
    except HTTPError as error:
        response = error
    with response:
        if response.status != expected_status:
            raise ValueError(f"{endpoint}: expected HTTP {expected_status}, got {response.status}")
        if response.headers.get_content_type() != "application/json":
            raise ValueError(f"{endpoint}: expected application/json")
        body = json.load(response)

    if not isinstance(body, dict):
        raise ValueError(f"{endpoint}: expected a JSON object")
    for field, value in expected.items():
        if body.get(field) != value:
            raise ValueError(
                f"{endpoint}: expected {field}={value!r}, got {body.get(field)!r}"
            )


def check_html(base_url, endpoint, expected_text):
    with urlopen(f"{base_url.rstrip('/')}{endpoint}", timeout=2) as response:
        if response.status != 200 or response.headers.get_content_type() != "text/html":
            raise ValueError(f"{endpoint}: expected HTTP 200 and text/html")
        page = response.read().decode("utf-8")
    if expected_text not in page:
        raise ValueError(f"{endpoint}: expected HTML containing {expected_text!r}")
    return page


def check_frontend(base_url):
    page = check_html(base_url, "/", '<div id="root"></div>')
    assets = re.findall(r'(?:src|href)="(/assets/[^"<>]+)"', page)
    if not any(asset.endswith(".js") for asset in assets):
        raise ValueError("Frontend has no built JavaScript bundle")
    for asset in assets:
        with urlopen(f"{base_url.rstrip('/')}{asset}", timeout=2) as response:
            if response.status != 200 or response.headers.get_content_type() == "text/html" or not response.read():
                raise ValueError(f"Missing or invalid frontend asset: {asset}")


def wait_for_health(base_url):
    """Allow a short startup period, then fail if health never passes."""
    for attempt in range(15):
        try:
            check_response(base_url, "/health", {"status": "ok"})
            return
        except (OSError, ValueError):
            if attempt == 14:
                raise
            time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5002")
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args()

    if not args.expected_version.strip() or not args.expected_commit.strip():
        parser.error("Expected version and commit must not be blank.")

    try:
        wait_for_health(args.base_url)
        check_frontend(args.base_url)
        check_response(args.base_url, "/frontend-version.json",
                       {"version": args.expected_version, "commit": args.expected_commit})
        check_response(args.base_url, "/api/activities", {})
        for removed in ("/add", "/subtract", "/multiply", "/divide", "/does-not-exist"):
            try:
                with urlopen(f"{args.base_url.rstrip('/')}{removed}", timeout=2) as response:
                    raise ValueError(f"{removed}: expected HTTP 404, got {response.status}")
            except HTTPError as error:
                if error.code != 404:
                    raise ValueError(f"{removed}: expected HTTP 404, got {error.code}") from error
        for path in ("/calories-bmi", "/bmi", "/calories-bmi/results", "/bmi/results", "/behind-the-numbers"):
            check_html(args.base_url, path, '<div id="root"></div>')
        fitness_input = {"units": "metric", "age": 30, "weight": 80,
                         "height": 180, "sex": "male", "activity": "moderate"}
        check_response(args.base_url, "/api/fitness", {
            "bmi": {"value": 24.69, "category": "Healthy weight"},
            "calories": {"resting_kcal": 1780, "maintenance_kcal": 2759,
                         "activity": "moderate", "activity_factor": 1.55,
                         "formula": "Mifflin–St Jeor"},
        }, payload=fitness_input)
        check_response(args.base_url, "/api/bmi", {
            "bmi": {"value": 24.69, "category": "Healthy weight"},
        }, payload={"units": "us", "age": 30, "weight": 80 / 0.45359237, "height": 180 / 2.54})
        check_response(args.base_url, "/api/calories", {"field": "age"},
                       expected_status=400, payload={**fitness_input, "age": 10})
        check_response(
            args.base_url,
            "/version",
            {"version": args.expected_version, "commit": args.expected_commit},
        )
    except (OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(
        f"PASS: frontend assets, fitness estimates, input errors, health, version {args.expected_version}, "
        f"and commit {args.expected_commit} verified at {args.base_url}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
