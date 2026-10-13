"""Validate release metadata; GitHub Actions also enforces operator authorization."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


VERSION_PATTERN = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


class ReleaseError(ValueError):
    """A release policy check failed."""


def parse_version(value):
    if not isinstance(value, str) or not VERSION_PATTERN.fullmatch(value):
        raise ReleaseError("Version must be MAJOR.MINOR.PATCH without leading zeroes or suffixes.")
    return tuple(int(part) for part in value.split("."))


def authorize(event, ref, actor, triggering_actor, operator):
    if event != "workflow_dispatch" or ref != "refs/heads/main":
        raise ReleaseError("Releases require a manual workflow dispatch from main.")
    operator = operator.strip().casefold()
    if not operator:
        raise ReleaseError("Configure the RELEASE_OPERATOR repository variable first.")
    if actor.casefold() != operator or triggering_actor.casefold() != operator:
        raise ReleaseError("Both the original operator and the rerun operator must be authorized.")


def release_versions(tags):
    versions = {}
    for tag in tags:
        # The v* namespace is reserved for successful stable releases.
        if tag.startswith("v"):
            versions[tag[1:]] = parse_version(tag[1:])
    return versions


def validate_candidate(version, metadata, changelog, tags):
    parse_version(version)
    if not isinstance(metadata, dict) or set(metadata) != {"change_type"}:
        raise ReleaseError('release.json must contain only "change_type".')
    change_type = metadata["change_type"]
    if change_type not in ("initial", "patch", "minor", "major"):
        raise ReleaseError("change_type must be initial, patch, minor, or major.")

    versions = release_versions(tags)
    if version in versions:
        raise ReleaseError(f"Version {version} already exists as a release tag.")
    previous = max(versions, key=versions.get) if versions else None
    if previous is None:
        if change_type != "initial":
            raise ReleaseError("No release tags exist: use initial for the first release.")
        expected = "1.0.0"
    else:
        if change_type == "initial":
            raise ReleaseError("initial is allowed only before the first successful release.")
        major, minor, patch = versions[previous]
        next_version = {
            "patch": (major, minor, patch + 1),
            "minor": (major, minor + 1, 0),
            "major": (major + 1, 0, 0),
        }[change_type]
        expected = ".".join(map(str, next_version))
    if version != expected:
        raise ReleaseError(f"Declared {change_type}: expected {expected}, found {version}.")

    # Require exactly one matching section with at least one nonempty bullet.
    sections = re.split(r"(?m)^## ", changelog)
    matches = []
    for section in sections[1:]:
        heading, _, body = section.partition("\n")
        if heading.strip() == f"[{version}]":
            matches.append(body)
    if len(matches) != 1 or not re.search(r"(?m)^- \S.*$", matches[0]):
        raise ReleaseError(f"CHANGELOG.md needs one '## [{version}]' section with a nonempty '- ' bullet.")

    return {
        "version": version,
        "previous_version": previous,
        "expected_version": expected,
        "change_type": change_type,
        "status": "validated",
    }


def git(root, *arguments):
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise ReleaseError(f"Git check failed: {' '.join(arguments)}. {result.stderr.strip()}")
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github", action="store_true", help="Require GitHub operator authorization.")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        if args.github:
            authorize(
                os.environ.get("GITHUB_EVENT_NAME", ""),
                os.environ.get("GITHUB_REF", ""),
                os.environ.get("GITHUB_ACTOR", ""),
                os.environ.get("GITHUB_TRIGGERING_ACTOR", ""),
                os.environ.get("RELEASE_OPERATOR", ""),
            )
        commit = git(root, "rev-parse", "HEAD")
        if args.github and commit != os.environ.get("GITHUB_SHA"):
            raise ReleaseError("Checked-out commit does not match the workflow's selected commit.")
        if git(root, "rev-parse", "--is-shallow-repository") != "false":
            raise ReleaseError("Full Git history and release tags are required.")
        result = validate_candidate(
            (root / "VERSION").read_text(encoding="utf-8").strip(),
            json.loads((root / "release.json").read_text(encoding="utf-8")),
            (root / "CHANGELOG.md").read_text(encoding="utf-8"),
            git(root, "tag", "--list").splitlines(),
        )
        if result["previous_version"]:
            # The baseline must belong to this commit's history, not another branch.
            git(root, "merge-base", "--is-ancestor", f"refs/tags/v{result['previous_version']}", commit)
        result["commit"] = commit
        result["mode"] = "github" if args.github else "local-preview"
        print(json.dumps(result, indent=2))
        return 0
    except (ReleaseError, OSError, ValueError) as error:
        print(f"Release validation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
