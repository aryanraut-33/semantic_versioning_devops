"""Verify correct responses from multiple backend instances through the frontend.

This is a small distribution check, not a load/performance test. Uses only stdlib.
"""

import argparse
from collections import Counter
import json
import sys
from urllib.request import Request, urlopen

FITNESS_INPUT = {"units": "metric", "age": 30, "weight": 80, "height": 180,
                 "sex": "male", "activity": "moderate"}
FITNESS_EXPECTED = {
    "bmi": {"value": 24.69, "category": "Healthy weight"},
    "calories": {"resting_kcal": 1780, "maintenance_kcal": 2759,
                 "activity": "moderate", "activity_factor": 1.55,
                 "formula": "Mifflin–St Jeor"},
}


def request_instance(base_url, path, expected, payload=None):
    headers = {"Connection": "close"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
    target = Request(base_url.rstrip("/") + path, data=data, headers=headers)
    with urlopen(target, timeout=5) as response:
        if response.status != 200 or response.headers.get_content_type() != "application/json":
            raise ValueError(f"{path}: expected HTTP 200 JSON")
        instance = response.headers.get("X-Instance-ID", "").strip()
        if not instance:
            raise ValueError(f"{path}: missing X-Instance-ID; rebuild and roll out the backend")
        body = json.load(response)
    if not isinstance(body, dict) or any(body.get(key) != value for key, value in expected.items()):
        raise ValueError(f"{path}: unexpected response from {instance}: {body!r}")
    return instance


def verify_distribution(counts, minimum, expected_instances=None):
    for path, samples in counts.items():
        if len(samples) < minimum:
            raise ValueError(f"{path}: reached only {len(samples)} instance(s); expected at least {minimum}")
        if expected_instances is not None and set(samples) != set(expected_instances):
            raise ValueError(f"{path}: observed instances do not match the supplied ready pod names")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5007")
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--samples", type=int, default=10000, help="Requests per endpoint")
    parser.add_argument("--min-instances", type=int, default=2)
    parser.add_argument("--expected-instances", nargs="+", help="Optional exact backend pod names")
    args = parser.parse_args()
    if args.min_instances < 1 or args.samples < args.min_instances:
        parser.error("Use positive instance count and samples >= min-instances")
    if not args.expected_version.strip() or not args.expected_commit.strip():
        parser.error("Expected version and commit must not be blank")
    cases = [
        ("/version", {"version": args.expected_version, "commit": args.expected_commit}, None),
        ("/api/fitness", FITNESS_EXPECTED, FITNESS_INPUT),
    ]
    counts = {path: Counter() for path, _, _ in cases}
    try:
        for _ in range(args.samples):
            for path, expected, payload in cases:
                instance = request_instance(args.base_url, path, expected, payload)
                counts[path][instance] += 1
        verify_distribution(counts, args.min_instances, args.expected_instances)
    except (OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    finally:
        print(json.dumps({path: dict(samples) for path, samples in counts.items()}, indent=2))
    print("PASS: both release identity and calculator responses verified across the required instances.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
