import json

import pytest

from scripts import validate_release
from scripts.validate_release import ReleaseError, authorize, github_release_commit, parse_version, validate_candidate


def candidate(version, change_type="patch", tags=("v1.0.1",), changelog=None):
    if changelog is None:
        changelog = f"# Changelog\n\n## [{version}]\n\n- Describe the change.\n"
    return validate_candidate(version, {"change_type": change_type}, changelog, tags)


@pytest.mark.parametrize("version,change_type", [("1.0.2", "patch"), ("1.1.0", "minor"), ("2.0.0", "major")])
def test_correct_increment(version, change_type):
    assert candidate(version, change_type)["expected_version"] == version


def test_patch_rejects_minor_increment():
    with pytest.raises(ReleaseError, match="expected 1.0.2, found 1.1.0"):
        candidate("1.1.0")


@pytest.mark.parametrize("version", ["1.0.0", "1.0.3", "2.0.0"])
def test_patch_rejects_wrong_increment(version):
    with pytest.raises(ReleaseError, match="expected 1.0.2"):
        candidate(version)


@pytest.mark.parametrize("version", ["", "v1.0.0", "01.0.0", "1.0", "1.0.0-rc.1", "1.0.0+build", "-1.0.0", "1.0.0\n"])
def test_invalid_or_unsupported_version(version):
    with pytest.raises(ReleaseError):
        parse_version(version)


def test_bootstrap():
    assert candidate("1.0.0", "initial", ())["previous_version"] is None


@pytest.mark.parametrize("version,change_type,tags", [
    ("1.0.1", "initial", ()),
    ("1.0.0", "patch", ()),
    ("1.0.2", "initial", ("v1.0.1",)),
])
def test_invalid_bootstrap(version, change_type, tags):
    with pytest.raises(ReleaseError):
        candidate(version, change_type, tags)


def test_reused_version():
    with pytest.raises(ReleaseError, match="already exists"):
        candidate("1.0.1")


def test_numeric_tag_order():
    result = candidate("1.10.1", tags=("v1.9.0", "v1.10.0", "sprint-3"))
    assert result["previous_version"] == "1.10.0"


@pytest.mark.parametrize("version,change_type", [("1.3.0", "minor"), ("2.0.0", "major")])
def test_lesser_components_reset(version, change_type):
    assert candidate(version, change_type, ("v1.2.9",))["version"] == version


@pytest.mark.parametrize("changelog", ["", "## [1.0.1]\n- Old change\n", "## [1.0.2]\n", "## [1.0.2]\n- \n", "## [1.0.2]\n- A\n## [1.0.2]\n- B\n"])
def test_missing_empty_or_duplicate_changelog(changelog):
    with pytest.raises(ReleaseError, match="CHANGELOG"):
        candidate("1.0.2", changelog=changelog)


@pytest.mark.parametrize("metadata", [{}, [], {"change_type": "fix"}, {"change_type": []}, {"change_type": "patch", "extra": True}])
def test_invalid_metadata(metadata):
    with pytest.raises(ReleaseError):
        validate_candidate("1.0.2", metadata, "## [1.0.2]\n- Fix\n", ("v1.0.1",))


def test_malformed_release_tag_fails_closed():
    with pytest.raises(ReleaseError):
        candidate("1.0.2", tags=("v1.0.1", "v01.0.2"))


def test_authorized_operator():
    authorize("workflow_dispatch", "refs/heads/main", "Aryan", "aryan", "aryan")


@pytest.mark.parametrize("event,ref,actor,rerunner,operator", [
    ("push", "refs/heads/main", "aryan", "aryan", "aryan"),
    ("workflow_dispatch", "refs/heads/feature", "aryan", "aryan", "aryan"),
    ("workflow_dispatch", "refs/heads/main", "other", "other", "aryan"),
    ("workflow_dispatch", "refs/heads/main", "aryan", "other", "aryan"),
    ("workflow_dispatch", "refs/heads/main", "other", "aryan", "aryan"),
    ("workflow_dispatch", "refs/heads/main", "aryan", "aryan", ""),
])
def test_unauthorized_attempt(event, ref, actor, rerunner, operator):
    with pytest.raises(ReleaseError):
        authorize(event, ref, actor, rerunner, operator)


@pytest.fixture
def automatic_release(tmp_path):
    payload = {
        "action": "completed",
        "workflow_run": {
            "name": "CI",
            "path": ".github/workflows/ci.yml",
            "event": "push",
            "status": "completed",
            "conclusion": "success",
            "head_branch": "main",
            "head_repository": {"full_name": "aryan/calculator"},
            "head_sha": "a" * 40,
            "actor": {"login": "Aryan"},
            "triggering_actor": {"login": "aryan"},
        },
    }
    environ = {
        "GITHUB_EVENT_NAME": "workflow_run",
        "GITHUB_EVENT_PATH": str(tmp_path / "event.json"),
        "GITHUB_REPOSITORY": "aryan/calculator",
        "GITHUB_REF": "refs/heads/main",
        # Simulate main advancing after the CI run began.
        "GITHUB_SHA": "b" * 40,
        "GITHUB_ACTOR": "aryan",
        "GITHUB_TRIGGERING_ACTOR": "aryan",
        "RELEASE_OPERATOR": "aryan",
    }
    return payload, environ


def write_event(environ, payload):
    from pathlib import Path

    Path(environ["GITHUB_EVENT_PATH"]).write_text(json.dumps(payload))


def test_automatic_release_selects_successful_ci_commit(automatic_release):
    payload, environ = automatic_release
    write_event(environ, payload)
    assert github_release_commit(environ) == "a" * 40


@pytest.mark.parametrize("field,value", [
    ("name", "Other workflow"),
    ("path", ".github/workflows/other.yml"),
    ("event", "pull_request"),
    ("event", "workflow_dispatch"),
    ("status", "in_progress"),
    ("conclusion", "failure"),
    ("conclusion", "cancelled"),
    ("conclusion", "skipped"),
    ("head_branch", "feature"),
    ("head_repository", {"full_name": "someone/fork"}),
    ("head_repository", None),
    ("head_sha", ""),
    ("head_sha", "main"),
    ("head_sha", None),
    ("actor", {"login": "other"}),
    ("triggering_actor", {"login": "other"}),
    ("triggering_actor", None),
])
def test_automatic_release_rejects_invalid_ci_context(automatic_release, field, value):
    payload, environ = automatic_release
    payload["workflow_run"][field] = value
    write_event(environ, payload)
    with pytest.raises(ReleaseError):
        github_release_commit(environ)


@pytest.mark.parametrize("field,value", [
    ("GITHUB_ACTOR", "other"),
    ("GITHUB_TRIGGERING_ACTOR", "other"),
    ("RELEASE_OPERATOR", ""),
    ("GITHUB_REPOSITORY", ""),
    ("GITHUB_EVENT_PATH", ""),
])
def test_automatic_release_rejects_invalid_release_context(automatic_release, field, value):
    payload, environ = automatic_release
    write_event(environ, payload)
    environ[field] = value
    with pytest.raises(ReleaseError):
        github_release_commit(environ)


@pytest.mark.parametrize("payload", [{}, [], {"action": "requested"}, {"action": "completed"}])
def test_automatic_release_requires_completed_event_payload(automatic_release, payload):
    _, environ = automatic_release
    write_event(environ, payload)
    with pytest.raises(ReleaseError):
        github_release_commit(environ)


def test_manual_release_still_uses_dispatch_commit(automatic_release):
    _, environ = automatic_release
    environ["GITHUB_EVENT_NAME"] = "workflow_dispatch"
    environ.pop("GITHUB_EVENT_PATH")
    assert github_release_commit(environ) == "b" * 40


@pytest.mark.parametrize("checkout_matches_ci", [True, False])
def test_validator_checks_checkout_against_ci_commit(
    automatic_release, tmp_path, monkeypatch, capsys, checkout_matches_ci
):
    payload, environ = automatic_release
    write_event(environ, payload)
    for key, value in environ.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(validate_release, "__file__", str(tmp_path / "scripts/validate_release.py"))
    monkeypatch.setattr(validate_release.sys, "argv", ["validate_release.py", "--github"])
    (tmp_path / "VERSION").write_text("1.0.1\n")
    (tmp_path / "release.json").write_text('{"change_type": "patch"}')
    (tmp_path / "CHANGELOG.md").write_text("## [1.0.1]\n- Compatible fix.\n")

    def git(root, *args):
        if args == ("rev-parse", "HEAD"):
            return ("a" if checkout_matches_ci else "b") * 40
        if args == ("rev-parse", "--is-shallow-repository"):
            return "false"
        if args == ("tag", "--list"):
            return "v1.0.0"
        assert args == ("merge-base", "--is-ancestor", "refs/tags/v1.0.0", "a" * 40)
        return ""

    monkeypatch.setattr(validate_release, "git", git)
    assert validate_release.main() == (0 if checkout_matches_ci else 1)
    output = capsys.readouterr()
    if checkout_matches_ci:
        assert json.loads(output.out)["commit"] == "a" * 40
    else:
        assert "Checked-out commit does not match" in output.err
