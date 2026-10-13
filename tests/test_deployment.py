"""Exercise replacement failures with a fake Docker engine; no containers are started."""

import json

import pytest

from scripts import deploy


@pytest.fixture
def engine(monkeypatch):
    containers = {}
    events = []

    def start(name, image, port, version, commit, restart="no"):
        events.append(("start-new", image))
        containers[name] = {"Image": image, "State": {"Running": True}, "Config": {"Labels": {
            deploy.LABEL: "true", "release-governance.version": version,
            "release-governance.commit": commit}}}

    def docker(*args):
        events.append(args)
        if args[0] == "rename":
            containers[args[2]] = containers.pop(args[1])
        elif args[0] in ("start", "stop"):
            containers[args[1]]["State"]["Running"] = args[0] == "start"
        elif args[0] == "rm":
            containers.pop(args[-1])
        return ""

    monkeypatch.setattr(deploy, "docker", docker)
    monkeypatch.setattr(deploy, "inspect_container", containers.get)
    monkeypatch.setattr(deploy, "start", start)
    monkeypatch.setattr(deploy, "smoke", lambda *args: None)
    monkeypatch.setattr(deploy, "show_logs", lambda name: None)
    return containers, events, start


def test_initial_deployment_records_exact_image(engine, tmp_path):
    containers, _, _ = engine
    state = tmp_path / "deployment.json"
    result = deploy.promote("sha256:new", "1.0.0", "new-commit", "1-1", state)
    assert containers[deploy.LIVE]["Image"] == "sha256:new"
    assert json.loads(state.read_text()) == result
    assert result["previous"] is None


def test_success_preserves_previous_container_and_identity(engine, tmp_path):
    containers, _, start = engine
    start(deploy.LIVE, "sha256:old", "5002", "1.0.0", "old-commit")
    result = deploy.promote("sha256:new", "1.0.1", "new-commit", "2-1", tmp_path / "state.json")
    assert result["previous"]["image_id"] == "sha256:old"
    assert result["previous"]["commit"] == "old-commit"
    assert not containers[result["previous"]["container"]]["State"]["Running"]


def test_failed_verification_restores_old_and_keeps_state(engine, tmp_path, monkeypatch):
    containers, _, start = engine
    start(deploy.LIVE, "sha256:old", "5002", "1.0.0", "old-commit")
    state = tmp_path / "state.json"
    state.write_text('"previous-state"')
    checked = []

    def smoke(port, version, commit):
        checked.append(commit)
        if commit == "new-commit":
            raise ValueError("wrong live version")

    monkeypatch.setattr(deploy, "smoke", smoke)
    with pytest.raises(ValueError, match="wrong live version"):
        deploy.promote("sha256:new", "1.0.1", "new-commit", "2-1", state)
    assert containers[deploy.LIVE]["Image"] == "sha256:old"
    assert containers[deploy.LIVE]["State"]["Running"]
    assert checked == ["new-commit", "old-commit"]
    assert json.loads(state.read_text()) == "previous-state"


def test_failed_first_deployment_leaves_no_live_container(engine, tmp_path, monkeypatch):
    containers, _, _ = engine
    monkeypatch.setattr(deploy, "smoke", lambda *args: (_ for _ in ()).throw(ValueError("failed")))
    state = tmp_path / "state.json"
    with pytest.raises(ValueError):
        deploy.promote("sha256:new", "1.0.0", "new-commit", "1-1", state)
    assert deploy.LIVE not in containers
    assert not state.exists()


def test_unmanaged_container_is_not_replaced(engine, tmp_path):
    containers, events, start = engine
    start(deploy.LIVE, "sha256:other", "5002", "1.0.0", "other")
    containers[deploy.LIVE]["Config"]["Labels"] = {}
    events.clear()
    with pytest.raises(ValueError, match="unmanaged"):
        deploy.promote("sha256:new", "1.0.0", "new", "1-1", tmp_path / "state.json")
    assert events == []


def test_failed_candidate_never_replaces_live_container(monkeypatch, tmp_path):
    (tmp_path / "VERSION").write_text("1.0.0\n")
    monkeypatch.setattr(deploy, "ROOT", tmp_path)
    for key, value in {"GITHUB_SHA": "abc", "GITHUB_RUN_ID": "1", "GITHUB_RUN_ATTEMPT": "1"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(deploy.subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(deploy, "show_logs", lambda name: None)
    calls = []
    monkeypatch.setattr(deploy, "docker", lambda *a: calls.append(a) or "sha256:new")
    monkeypatch.setattr(deploy, "start", lambda *a, **k: None)
    monkeypatch.setattr(deploy, "inspect_container", lambda name: {
        "NetworkSettings": {"Ports": {"8000/tcp": [{"HostPort": "49152"}]}}})

    def fail(*args):
        raise ValueError("candidate failed")

    monkeypatch.setattr(deploy, "smoke", fail)
    monkeypatch.setattr(deploy, "promote", lambda *a: pytest.fail("Must not promote failed candidate"))
    with pytest.raises(ValueError, match="candidate failed"):
        deploy.deploy()
    assert ("rm", "--force", "release-api-candidate-1-1") in calls
    assert not any(deploy.LIVE in command for command in calls)


def test_failed_container_start_restores_previous(engine, tmp_path, monkeypatch):
    containers, _, start = engine
    start(deploy.LIVE, "sha256:old", "5002", "1.0.0", "old-commit")

    def fail(*args, **kwargs):
        raise ValueError("port unavailable")

    monkeypatch.setattr(deploy, "start", fail)
    with pytest.raises(ValueError, match="port unavailable"):
        deploy.promote("sha256:new", "1.0.1", "new", "2-1", tmp_path / "state.json")
    assert containers[deploy.LIVE]["Image"] == "sha256:old"
    assert containers[deploy.LIVE]["State"]["Running"]
