import pytest

from scripts.validate_release import ReleaseError, authorize, parse_version, validate_candidate


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
