"""Verify the packaged API over HTTP using only the Python standard library."""

import argparse
import json
import sys
import time
from urllib.error import HTTPError
from urllib.request import urlopen


def check_response(base_url, endpoint, expected, expected_status=200):
    """Check required fields while allowing compatible additional fields."""
    try:
        response = urlopen(f"{base_url.rstrip('/')}{endpoint}", timeout=2)
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
        check_html(args.base_url, "/", "<h1>Arithmetic Calculator</h1>")
        for operation, result in [("add", 8), ("subtract", 4), ("multiply", 12), ("divide", 3)]:
            check_response(
                args.base_url,
                f"/{operation}?a=6&b=2",
                {"operation": operation, "a": 6, "b": 2, "result": result},
            )
        check_response(
            args.base_url, "/divide?a=6&b=0", {"error": "Cannot divide by zero."}, expected_status=400
        )
        check_html(args.base_url, "/add?a=6&b=2&format=html", '<output id="result">8.0</output>')
        check_response(
            args.base_url,
            "/version",
            {"version": args.expected_version, "commit": args.expected_commit},
        )
    except (OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(
        f"PASS: calculator UI, arithmetic, input error, health, version {args.expected_version}, "
        f"and commit {args.expected_commit} verified at {args.base_url}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
