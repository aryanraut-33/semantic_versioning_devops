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


def authorize(event, ref, actor, triggering_actor, operator, *, workflow_run=None, repository=""):
    source_actors = []
    if event == "workflow_run":
        run = workflow_run if isinstance(workflow_run, dict) else {}
        source_repository = run.get("head_repository") or {}
        if (
            run.get("name") != "CI"
            or run.get("path") != ".github/workflows/ci.yml"
            or run.get("event") != "push"
            or run.get("status") != "completed"
            or run.get("conclusion") != "success"
            or run.get("head_branch") != "main"
            or not repository
            or not isinstance(source_repository, dict)
            or source_repository.get("full_name") != repository
        ):
            raise ReleaseError("Automatic releases require successful push CI on main in this repository.")
        for field in ("actor", "triggering_actor"):
            identity = run.get(field)
            source_actors.append(identity.get("login", "") if isinstance(identity, dict) else "")
    elif event != "workflow_dispatch" or ref != "refs/heads/main":
        raise ReleaseError("Releases require manual dispatch from main or successful push CI on main.")
    operator = operator.strip().casefold()
    if not operator:
        raise ReleaseError("Configure the RELEASE_OPERATOR repository variable first.")
    if actor.casefold() != operator or triggering_actor.casefold() != operator:
        raise ReleaseError("Both the original operator and the rerun operator must be authorized.")
    if any(not isinstance(login, str) or login.casefold() != operator for login in source_actors):
        raise ReleaseError("Both the CI operator and the CI rerun operator must be authorized.")


def github_release_commit(environ=None):
    """Authorize GitHub context and select the exact source commit for this release."""
    environ = os.environ if environ is None else environ
    event = environ.get("GITHUB_EVENT_NAME", "")
    run = None
    if event == "workflow_run":
        event_path = environ.get("GITHUB_EVENT_PATH")
        if not event_path:
            raise ReleaseError("GitHub workflow_run event payload is required.")
        payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("action") != "completed":
            raise ReleaseError("A completed workflow_run event is required.")
        run = payload.get("workflow_run")
    authorize(
        event,
        environ.get("GITHUB_REF", ""),
        environ.get("GITHUB_ACTOR", ""),
        environ.get("GITHUB_TRIGGERING_ACTOR", ""),
        environ.get("RELEASE_OPERATOR", ""),
        workflow_run=run,
        repository=environ.get("GITHUB_REPOSITORY", ""),
    )
    commit = run.get("head_sha") if event == "workflow_run" else environ.get("GITHUB_SHA", "")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ReleaseError("Release source must be a full Git commit SHA.")
    return commit


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
        selected_commit = github_release_commit() if args.github else None
        commit = git(root, "rev-parse", "HEAD")
        if args.github and commit != selected_commit:
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
