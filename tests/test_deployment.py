"""Test pair promotion and recovery without running Docker."""

import json
import pytest

from scripts import deploy

IMAGES = {"frontend": "sha256:front-new", "backend": "sha256:back-new"}


@pytest.fixture
def engine(monkeypatch):
    events = []
    monkeypatch.setattr(deploy, "docker", lambda *a, **k: "")
    monkeypatch.setattr(deploy, "up", lambda file, project: events.append(("up", str(file))))
    monkeypatch.setattr(deploy, "down", lambda file, project: events.append(("down", str(file))))
    monkeypatch.setattr(deploy, "logs", lambda *a: None)
    monkeypatch.setattr(deploy, "smoke", lambda *a: events.append(("smoke", a[2])))
    monkeypatch.setattr(deploy, "verify_images", lambda *a: events.append(("verify", a[2])))
    return events


def old_state(tmp_path):
    manifest = tmp_path / "old.json"
    manifest.write_text("{}")
    previous = {"manifest": str(manifest), "version": "2.0.0", "commit": "old",
                "images": {"frontend": "sha256:front-old", "backend": "sha256:back-old"}}
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"current": previous}))
    return state, previous


def test_initial_deployment_records_both_exact_images(engine, tmp_path):
    state = tmp_path / "state.json"
    result = deploy.promote(tmp_path / "new.json", IMAGES, "2.0.0", "new", state)
    assert result["current"]["images"] == IMAGES
    assert result["previous"] is None
    assert json.loads(state.read_text()) == result
    assert ("verify", IMAGES) in engine


def test_success_preserves_previous_pair_manifest(engine, tmp_path):
    state, previous = old_state(tmp_path)
    result = deploy.promote(tmp_path / "new.json", IMAGES, "2.0.1", "new", state)
    assert result["previous"] == previous
    assert engine.index(("down", previous["manifest"])) < engine.index(("up", str(tmp_path / "new.json")))


def test_failed_verification_restores_both_images_and_keeps_state(engine, tmp_path, monkeypatch):
    state, previous = old_state(tmp_path)
    original = state.read_text()
    def smoke(port, version, commit):
        engine.append(("smoke", commit))
        if commit == "new":
            raise ValueError("wrong live version")
    monkeypatch.setattr(deploy, "smoke", smoke)
    with pytest.raises(ValueError, match="wrong live version"):
        deploy.promote(tmp_path / "new.json", IMAGES, "2.0.1", "new", state)
    assert ("up", previous["manifest"]) in engine
    assert engine[-1] == ("verify", previous["images"])
    assert state.read_text() == original


def test_failed_start_restores_previous_pair(engine, tmp_path, monkeypatch):
    state, previous = old_state(tmp_path)
    def up(file, project):
        engine.append(("up", str(file)))
        if str(file).endswith("new.json"):
            raise ValueError("frontend failed")
    monkeypatch.setattr(deploy, "up", up)
    with pytest.raises(ValueError, match="frontend failed"):
        deploy.promote(tmp_path / "new.json", IMAGES, "2.0.1", "new", state)
    assert ("up", previous["manifest"]) in engine


def test_failed_first_deployment_does_not_record_success(engine, tmp_path, monkeypatch):
    monkeypatch.setattr(deploy, "smoke", lambda *a: (_ for _ in ()).throw(ValueError("failed")))
    state = tmp_path / "state.json"
    with pytest.raises(ValueError):
        deploy.promote(tmp_path / "new.json", IMAGES, "2.0.0", "new", state)
    assert not state.exists()
    assert engine[-1] == ("down", str(tmp_path / "new.json"))


def test_unknown_live_project_is_not_modified(engine, tmp_path, monkeypatch):
    monkeypatch.setattr(deploy, "docker", lambda *a, **k: "existing")
    with pytest.raises(ValueError, match="without deployment state"):
        deploy.promote(tmp_path / "new.json", IMAGES, "2.0.0", "new", tmp_path / "state.json")
    assert engine == []


def test_legacy_live_container_requires_explicit_migration(engine, tmp_path, monkeypatch):
    monkeypatch.setattr(deploy, "docker", lambda *a, **k: "legacy" if "name=^/release-governance-app$" in a else "")
    with pytest.raises(ValueError, match="legacy"):
        deploy.promote(tmp_path / "new.json", IMAGES, "2.0.0", "new", tmp_path / "state.json")
    assert engine == []


def test_image_mismatch_is_rejected(monkeypatch):
    monkeypatch.setattr(deploy, "compose", lambda *a: "container")
    monkeypatch.setattr(deploy, "docker", lambda *a: "sha256:wrong")
    with pytest.raises(ValueError, match="tested image"):
        deploy.verify_images("stack.json", "test", IMAGES)


def test_candidate_failure_never_promotes(monkeypatch, tmp_path):
    (tmp_path / "VERSION").write_text("2.0.0")
    monkeypatch.setattr(deploy, "ROOT", tmp_path)
    monkeypatch.setattr(deploy, "STATE", tmp_path / "state.json")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.setattr(deploy.subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(deploy.subprocess, "check_output", lambda *a, **k: "selected-commit")
    monkeypatch.setattr(deploy, "docker", lambda *a, **k: "sha256:test")
    monkeypatch.setattr(deploy, "write_manifest", lambda path, *a: path)
    monkeypatch.setattr(deploy, "up", lambda *a: None)
    monkeypatch.setattr(deploy, "compose", lambda *a: "127.0.0.1:49152")
    monkeypatch.setattr(deploy, "logs", lambda *a: None)
    cleanup = []
    monkeypatch.setattr(deploy, "down", lambda *a: cleanup.append(a))
    monkeypatch.setattr(deploy, "smoke", lambda *a: (_ for _ in ()).throw(ValueError("candidate failed")))
    monkeypatch.setattr(deploy, "promote", lambda *a: pytest.fail("Must not promote failed candidate"))
    with pytest.raises(ValueError, match="candidate failed"):
        deploy.deploy()
    assert cleanup[0][1] == "calfit-candidate-123-1"


def test_manifest_pins_images_and_isolates_networks(monkeypatch, tmp_path):
    config = {"name": "original", "networks": {"default": {"name": "original_default"}},
              "services": {name: {"build": {"context": "/source"}, "image": "mutable-tag"} for name in IMAGES}}
    monkeypatch.setattr(deploy, "docker", lambda *a, **k: json.dumps(config))
    path = deploy.write_manifest(tmp_path / "stack.json", IMAGES, "5004")
    saved = json.loads(path.read_text())
    assert "name" not in saved
    assert saved["networks"] == {"default": {}}
    for service in IMAGES:
        assert saved["services"][service]["image"] == IMAGES[service]
        assert "build" not in saved["services"][service]


def test_builds_selected_checkout_and_records_two_images(monkeypatch, tmp_path):
    (tmp_path / "VERSION").write_text("2.0.0")
    monkeypatch.setattr(deploy, "ROOT", tmp_path)
    monkeypatch.setattr(deploy, "STATE", tmp_path / "state.json")
    monkeypatch.setenv("GITHUB_RUN_ID", "234")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.setenv("GITHUB_SHA", "different-workflow-sha")
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "outputs"))
    monkeypatch.setattr(deploy.subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(deploy.subprocess, "check_output", lambda *a, **k: "selected-commit")
    builds = []
    def docker(*args, **kwargs):
        if "build" in args:
            builds.append(kwargs["env"])
        if args[:2] == ("image", "inspect"):
            return IMAGES["frontend" if "frontend" in args[2] else "backend"]
        return ""
    monkeypatch.setattr(deploy, "docker", docker)
    monkeypatch.setattr(deploy, "write_manifest", lambda path, *a: path)
    monkeypatch.setattr(deploy, "up", lambda *a: None)
    monkeypatch.setattr(deploy, "down", lambda *a: None)
    monkeypatch.setattr(deploy, "logs", lambda *a: None)
    monkeypatch.setattr(deploy, "compose", lambda *a: "127.0.0.1:49152")
    checks = []
    monkeypatch.setattr(deploy, "smoke", lambda *a: checks.append(a))
    monkeypatch.setattr(deploy, "verify_images", lambda *a: None)
    promotions = []
    monkeypatch.setattr(deploy, "promote", lambda *a: promotions.append(a) or {})
    deploy.deploy()
    assert builds[0]["APP_COMMIT"] == "selected-commit"
    assert checks == [("49152", "2.0.0", "selected-commit")]
    assert promotions[0][1] == IMAGES
    evidence = (tmp_path / "outputs").read_text()
    assert "frontend_image=sha256:front-new" in evidence
    assert "backend_image=sha256:back-new" in evidence
    assert "commit=selected-commit" in evidence
