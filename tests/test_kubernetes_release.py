"""Release recovery and evidence checks with subprocesses mocked; no cluster needed."""

from contextlib import contextmanager
import json
import subprocess

import pytest

from scripts import deploy_kubernetes as deploy

SHA = "sha256:" + "a" * 64


@pytest.mark.parametrize("value", [SHA, "containerd://" + SHA, "docker.io/library/calfit@" + SHA])
def test_digest_normalizes_runtime_formats(value):
    assert deploy.digest(value) == SHA


def test_unknown_digest_is_rejected():
    with pytest.raises(ValueError):
        deploy.digest("calfit:latest")


@pytest.mark.parametrize("repo_digests", [None, [], ["docker.io/library/calfit@" + SHA]])
def test_optional_runtime_repo_digests_can_be_null(repo_digests):
    assert deploy.runtime_digests({"id": SHA, "repoDigests": repo_digests}) == [SHA]


def test_runtime_digest_missing_optional_field():
    assert deploy.runtime_digests({"id": SHA}) == [SHA]


def test_null_required_image_id_still_fails():
    with pytest.raises(ValueError, match="Unrecognised runtime image identity"):
        deploy.runtime_digests({"id": None, "repoDigests": None})


@pytest.mark.parametrize("status", [None, {}, {"conditions": None, "currentMetrics": None},
    {"conditions": [{"type": "AbleToScale", "status": "True"},
                    {"type": "ScalingActive", "status": "True"}], "currentMetrics": None}])
def test_uninitialised_hpa_reports_retryable_metrics_error(monkeypatch, status):
    monkeypatch.setattr(deploy, "get", lambda *a: {"status": status})
    with pytest.raises(ValueError, match="numeric CPU"):
        deploy.hpa_status("candidate")


def test_wait_ready_retries_null_metrics_until_numeric_cpu_available(monkeypatch):
    states = iter([
        {"status": {"conditions": None, "currentMetrics": None}},
        {"spec": {"minReplicas": 2, "maxReplicas": 4,
                  "scaleTargetRef": {"name": "calfit-backend"},
                  "metrics": [{"resource": {"name": "cpu", "target": {"averageUtilization": 60}}}]},
         "status": {"conditions": [{"type": "AbleToScale", "status": "True"},
                                    {"type": "ScalingActive", "status": "True"}],
                    "currentMetrics": [{"resource": {"name": "cpu", "current": {"averageUtilization": 0}}}],
                    "desiredReplicas": 2, "currentReplicas": 2}},
    ])
    monkeypatch.setattr(deploy, "get", lambda *a: next(states))
    monkeypatch.setattr(deploy, "kube", lambda *a: "")
    monkeypatch.setattr(deploy, "ready_pods", lambda *a: {"backend": []})
    monkeypatch.setattr(deploy.time, "monotonic", lambda: 0)
    sleeps = []
    monkeypatch.setattr(deploy.time, "sleep", sleeps.append)
    result = deploy.wait_ready("candidate")
    assert result["hpa"]["cpu_percent"] == 0
    assert sleeps == [5]


def test_snapshot_sanitizing_leaves_backend_scale_to_hpa():
    resource = {"kind": "Deployment", "metadata": {"name": "calfit-backend", "uid": "old",
                "annotations": {"kubectl.kubernetes.io/last-applied-configuration": "old"}},
                "spec": {"replicas": 4, "template": {"example": True}}, "status": {"readyReplicas": 4}}
    cleaned = deploy.clean(resource)
    assert "replicas" not in cleaned["spec"]
    assert "status" not in cleaned and "uid" not in cleaned["metadata"]
    assert resource["spec"]["replicas"] == 4


def test_render_isolates_candidate_and_preserves_hpa(monkeypatch):
    raw = """kind: Namespace
metadata: {name: calfit}
---
kind: Deployment
metadata: {name: calfit-backend}
spec:
  template:
    spec:
      containers: [{name: backend, image: old}]
---
kind: HorizontalPodAutoscaler
metadata: {name: calfit-backend}
spec: {minReplicas: 2, maxReplicas: 4}
"""
    monkeypatch.setattr(deploy, "run", lambda *a, **k: raw)
    resources = deploy.render("candidate", {"backend": {"tag": "calfit-backend:unique"}})
    assert resources[0]["metadata"]["name"] == "candidate"
    assert resources[1]["metadata"]["namespace"] == "candidate"
    container = resources[1]["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == "calfit-backend:unique" and container["imagePullPolicy"] == "Never"
    assert resources[2]["spec"]["maxReplicas"] == 4


def test_failed_live_check_restores_previous_and_still_fails(monkeypatch):
    events = []
    monkeypatch.setattr(deploy, "apply", lambda ns, resources: events.append(resources))
    def fail():
        raise ValueError("wrong live identity")
    with pytest.raises(ValueError, match="wrong live identity"):
        deploy.promote(["new"], ["previous"], fail, lambda: events.append("verified previous"))
    assert events == [["new"], ["previous"], "verified previous"]


def test_partial_apply_failure_also_restores_previous(monkeypatch):
    events = []
    def apply(ns, resources):
        events.append(resources)
        if resources == ["new"]:
            raise ValueError("rollout failed")
    monkeypatch.setattr(deploy, "apply", apply)
    with pytest.raises(ValueError, match="rollout failed"):
        deploy.promote(["new"], ["old"], lambda: None, lambda: events.append("checked"))
    assert events == [["new"], ["old"], "checked"]


def test_recovery_failure_is_not_reported_as_success(monkeypatch):
    monkeypatch.setattr(deploy, "apply", lambda *a: None)
    def fail():
        raise ValueError("verification failed")
    with pytest.raises(ValueError):
        deploy.promote(["new"], ["old"], fail, fail)


def test_hpa_with_missing_metrics_is_rejected(monkeypatch):
    monkeypatch.setattr(deploy, "get", lambda *a: {"status": {"conditions": [
        {"type": "AbleToScale", "status": "True"}, {"type": "ScalingActive", "status": "True"}]}})
    with pytest.raises(ValueError, match="numeric CPU"):
        deploy.hpa_status("candidate")


def test_ready_pod_with_correct_tag_but_wrong_bytes_is_rejected(monkeypatch):
    pod = {"metadata": {"name": "frontend-a"},
           "spec": {"containers": [{"image": "frontend:unique"}]},
           "status": {"conditions": [{"type": "Ready", "status": "True"}],
                      "containerStatuses": [{"imageID": SHA}]}}
    monkeypatch.setattr(deploy, "kube", lambda *a, **k: json.dumps({"items": [pod]}))
    with pytest.raises(ValueError, match="Untested image"):
        deploy.ready_pods("candidate", {"frontend": {"tag": "frontend:unique",
                         "runtime_digests": ["sha256:" + "b" * 64]}})


def test_failed_first_deployment_cleans_resources_without_deleting_namespace(monkeypatch):
    calls = []
    monkeypatch.setattr(deploy, "apply", lambda *a: None)
    monkeypatch.setattr(deploy, "kube", lambda *a, **k: calls.append(a))
    resources = [{"kind": "Namespace", "metadata": {"name": "calfit"}},
                 {"kind": "Deployment", "metadata": {"name": "calfit-backend"}}]
    def fail():
        raise ValueError("failed")
    with pytest.raises(ValueError):
        deploy.promote(resources, [], fail, lambda: None)
    assert len(calls) == 1 and calls[0][2] == "Deployment"


def test_authorization_failure_happens_before_docker_or_kubernetes(monkeypatch):
    calls = []
    def run(*args, **kwargs):
        calls.append(args)
        raise subprocess.CalledProcessError(1, args, stderr="unauthorized")
    monkeypatch.setattr(deploy, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        deploy.deploy({})
    assert len(calls) == 1 and calls[0][-1] == "--github"


def test_failed_candidate_never_snapshots_or_promotes_live(monkeypatch, tmp_path):
    commit = "b" * 40
    calls = []
    def run(*args, **kwargs):
        calls.append(args)
        if args[-1] == "--github":
            return json.dumps({"version": "2.1.0", "commit": commit})
        if args[:3] == ("docker", "image", "inspect"):
            return SHA
        if "inspecti" in args:
            return json.dumps({"status": {"id": SHA}})
        return ""
    monkeypatch.setattr(deploy, "run", run)
    monkeypatch.setattr(deploy, "STATE_DIR", tmp_path)
    monkeypatch.setenv("GITHUB_RUN_ID", "42")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.setenv("RELEASE_K6_PROFILE", "smoke")
    monkeypatch.setattr(deploy, "render", lambda *a: [])
    monkeypatch.setattr(deploy, "apply", lambda *a: None)
    monkeypatch.setattr(deploy, "wait_ready", lambda *a: {})
    monkeypatch.setattr(deploy, "collect", lambda *a: None)
    @contextmanager
    def forward(*args):
        yield "http://localhost:1"
    monkeypatch.setattr(deploy, "forward", forward)
    monkeypatch.setattr(deploy, "smoke", lambda *a: None)
    def fail(*args):
        raise ValueError("candidate failed")
    monkeypatch.setattr(deploy, "k6_check", fail)
    monkeypatch.setattr(deploy, "snapshot", lambda: pytest.fail("Live must remain untouched"))
    with pytest.raises(ValueError, match="candidate failed"):
        deploy.deploy({})
    builds = [call for call in calls if call[:2] == ("docker", "build")]
    assert len(builds) == 2 and all(f"APP_COMMIT={commit}" in call for call in builds)
    assert any("delete" in call and "calfit-candidate-42-1" in call for call in calls)
