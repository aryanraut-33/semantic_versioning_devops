"""Authorized local Kubernetes releases. All mutations happen only when invoked.

Requires the runner user's calfit Minikube profile, kubectl, Docker, k6 and PyYAML.
The existing Compose deployment script is retained for historical recovery.
"""

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback
from urllib.request import urlopen

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = "calfit"
LIVE = "calfit"
STATE_DIR = Path.home() / ".local/state/semantic_versioning_devops/kubernetes"
ARTIFACTS = ROOT / ".artifacts/release"
ROLES = ("frontend", "backend")


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run(*args, input=None, env=None, timeout=300):
    result = subprocess.run(list(args), cwd=ROOT, input=input, text=True,
                            capture_output=True, env=env, timeout=timeout, check=True)
    return result.stdout.strip()


def kube(namespace, *args, **kwargs):
    return run("kubectl", "--context", CONTEXT, "--namespace", namespace, *args, **kwargs)


def get(namespace, resource):
    return json.loads(kube(namespace, "get", resource, "-o", "json"))


def digest(value):
    match = re.search(r"sha256:[0-9a-f]{64}$", value) if isinstance(value, str) else None
    if not match:
        raise ValueError(f"Unrecognised runtime image identity: {value}")
    return match.group()


def runtime_digests(status):
    # CRI may return "repoDigests": null for locally loaded images.
    # Keep the required image ID check; an absent optional list isn't an error.
    return sorted({digest(value) for value in [status["id"], *(status.get("repoDigests") or [])]})


def clean(resource):
    result = deepcopy(resource)
    result.pop("status", None)
    metadata = result["metadata"]
    for key in ("uid", "resourceVersion", "generation", "creationTimestamp", "managedFields"):
        metadata.pop(key, None)
    if metadata.get("annotations"):
        metadata["annotations"].pop("kubectl.kubernetes.io/last-applied-configuration", None)
    if result["kind"] == "Deployment" and metadata["name"] == "calfit-backend":
        result["spec"].pop("replicas", None)
    return result


def render(namespace, images):
    resources = [item for item in yaml.safe_load_all(run("kubectl", "kustomize", "k8s")) if item]
    for item in resources:
        if item["kind"] == "Namespace":
            item["metadata"]["name"] = namespace
        else:
            item["metadata"]["namespace"] = namespace
        if item["kind"] == "Deployment":
            role = item["metadata"]["name"].removeprefix("calfit-")
            for container in item["spec"]["template"]["spec"]["containers"]:
                container["image"] = images[role]["tag"]
                container["imagePullPolicy"] = "Never"
    return resources


def apply(namespace, resources):
    # Bootstrap namespace/Services before Nginx resolves the backend Service.
    ordered = sorted(resources, key=lambda x: {"Namespace": 0, "ConfigMap": 1,
                     "Service": 2, "HorizontalPodAutoscaler": 3, "Deployment": 4}[x["kind"]])
    for item in ordered:
        kube(namespace, "apply", "-f", "-", input=json.dumps(item))


def ready_pods(namespace, images=None):
    result = {}
    for role in ROLES:
        pods = json.loads(kube(namespace, "get", "pods", "-l", f"app=calfit-{role}", "-o", "json")).get("items") or []
        pods = [pod for pod in pods if not pod["metadata"].get("deletionTimestamp")]
        if len(pods) < (2 if role == "backend" else 1):
            raise ValueError(f"Not enough {role} pods")
        result[role] = []
        for pod in pods:
            if not any(c["type"] == "Ready" and c["status"] == "True"
                       for c in (pod.get("status") or {}).get("conditions") or []):
                raise ValueError(f"Pod {pod['metadata']['name']} is not ready")
            statuses = pod["status"].get("containerStatuses") or []
            if len(statuses) != 1:
                raise ValueError("Expected one application container per pod")
            actual = digest(statuses[0]["imageID"])
            if images:
                container = pod["spec"]["containers"][0]
                if container["image"] != images[role]["tag"] or actual not in images[role]["runtime_digests"]:
                    raise ValueError(f"Untested image in {pod['metadata']['name']}")
            result[role].append({"pod": pod["metadata"]["name"], "image_digest": actual})
    return result


def hpa_status(namespace):
    hpa = get(namespace, "hpa/calfit-backend")
    state = hpa.get("status") or {}
    active = {c["type"]: c["status"] for c in state.get("conditions") or []}
    cpu = None
    for metric in state.get("currentMetrics") or []:
        resource = metric.get("resource") or {}
        if resource.get("name") == "cpu":
            cpu = (resource.get("current") or {}).get("averageUtilization")
            break
    if active.get("AbleToScale") != "True" or active.get("ScalingActive") != "True" or cpu is None:
        raise ValueError("HPA is not active with numeric CPU metrics")
    spec = hpa.get("spec") or {}
    targets = [(metric["resource"].get("target") or {}).get("averageUtilization")
               for metric in spec.get("metrics") or [] if (metric.get("resource") or {}).get("name") == "cpu"]
    if (spec.get("minReplicas"), spec.get("maxReplicas"), targets,
        spec.get("scaleTargetRef", {}).get("name")) != (2, 4, [60], "calfit-backend"):
        raise ValueError("HPA does not match the release policy: calfit-backend, 2–4 replicas, 60% CPU")
    return {"cpu_percent": cpu, "desired": state.get("desiredReplicas"),
            "current": state.get("currentReplicas"), "spec": spec}


def wait_ready(namespace, images=None):
    for role in ROLES:
        kube(namespace, "rollout", "status", f"deployment/calfit-{role}", "--timeout=180s")
    deadline = time.monotonic() + 180
    while True:
        try:
            return {"pods": ready_pods(namespace, images), "hpa": hpa_status(namespace)}
        except ValueError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(5)


@contextmanager
def forward(namespace, log_path):
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(["kubectl", "--context", CONTEXT, "-n", namespace,
            "port-forward", "--address", "127.0.0.1", "service/calfit-frontend", ":80"],
            stdout=log, stderr=subprocess.STDOUT, text=True)
        try:
            deadline = time.monotonic() + 60
            while True:
                match = re.search(r"Forwarding from 127\.0\.0\.1:(\d+)", log_path.read_text())
                if match:
                    yield f"http://127.0.0.1:{match.group(1)}"
                    break
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise ValueError(f"Port-forward failed; inspect {log_path}")
                time.sleep(0.5)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def smoke(url, version, commit):
    for script in ("smoke_test.py", "check_load_balancing.py"):
        output = run(sys.executable, str(ROOT / "scripts" / script), "--base-url", url,
                     "--expected-version", version, "--expected-commit", commit)
        print(output, flush=True)


def k6_check(namespace, url, version, commit, profile, path):
    env = {**os.environ, "BASE_URL": url, "EXPECTED_VERSION": version,
           "EXPECTED_COMMIT": commit, "PROFILE": profile, "REPORT_PATH": str(path)}
    history = []
    baseline = hpa_status(namespace)
    minimum = baseline["spec"]["minReplicas"]
    if profile == "autoscale":
        deadline = time.monotonic() + 300
        while True:
            baseline = hpa_status(namespace)
            ready = get(namespace, "deployment/calfit-backend")["status"].get("readyReplicas", 0)
            if baseline["desired"] == minimum and ready == minimum:
                history.append({"time": now(), "phase": "baseline", "ready": ready, **baseline})
                break
            if time.monotonic() >= deadline:
                raise ValueError("Candidate did not settle at minimum replicas before the load test")
            time.sleep(5)
    with path.with_suffix(".log").open("w") as log:
        process = subprocess.Popen(["k6", "run", str(ROOT / "load-tests/calfit.js")],
            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, text=True)
        try:
            deadline = time.monotonic() + 1800
            while process.poll() is None:
                try:
                    sample = hpa_status(namespace)
                    sample["ready"] = get(namespace, "deployment/calfit-backend")["status"].get("readyReplicas", 0)
                    history.append({"time": now(), **sample})
                except (ValueError, subprocess.CalledProcessError) as error:
                    history.append({"time": now(), "error": str(error)})
                if time.monotonic() >= deadline:
                    raise ValueError("k6 exceeded release time budget")
                time.sleep(5)
            if process.returncode:
                raise ValueError(f"k6 failed (exit {process.returncode}); inspect {path.with_suffix('.log')}")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            write_json(path.with_name(path.stem + "-hpa.json"), history)
    summary = json.loads(path.read_text())
    if (summary.get("expected_version"), summary.get("expected_commit"), summary.get("profile")) != (version, commit, profile):
        raise ValueError("k6 evidence identity/profile mismatch")
    if not summary.get("results", {}).get("requests") or summary["results"].get("failed_thresholds"):
        raise ValueError("k6 report is missing results or has failed thresholds")
    increased = any(s.get("desired", 0) > minimum and s.get("ready", 0) > minimum for s in history)
    if profile == "autoscale":
        if not increased:
            raise ValueError("Candidate autoscaling test did not observe a ready replica increase")
        deadline = time.monotonic() + 300
        while True:
            state = hpa_status(namespace)
            ready = get(namespace, "deployment/calfit-backend")["status"].get("readyReplicas", 0)
            if state["desired"] == minimum and ready == minimum:
                break
            if time.monotonic() >= deadline:
                raise ValueError("Candidate did not scale back to minimum within the verification window")
            time.sleep(5)
    return {"profile": profile, "scale_up_observed": increased,
            "scale_down_verified": profile == "autoscale", "summary": str(path.name)}


def snapshot():
    items = []
    for kind, name in (("deployment", "calfit-backend"), ("deployment", "calfit-frontend"),
                       ("service", "calfit-backend"), ("service", "calfit-frontend"),
                       ("hpa", "calfit-backend")):
        raw = kube(LIVE, "get", f"{kind}/{name}", "--ignore-not-found", "-o", "json")
        if raw:
            items.append(clean(json.loads(raw)))
    if not items:
        return []
    if len(items) != 5:
        raise ValueError("Existing calfit deployment is incomplete; repair before release")
    frontend = next(x for x in items if x["kind"] == "Deployment" and x["metadata"]["name"] == "calfit-frontend")
    for volume in frontend["spec"]["template"]["spec"].get("volumes") or []:
        if "configMap" in volume:
            items.append(clean(get(LIVE, "configmap/" + volume["configMap"]["name"])))
    return items


def collect(namespace, prefix):
    """Best-effort diagnostics; never let log collection block recovery."""
    commands = {
        "resources": ("get", "deployments,pods,services,hpa,endpointslices", "-o", "json"),
        "events": ("get", "events", "--sort-by=.lastTimestamp"),
        "backend-log": ("logs", "-l", "app=calfit-backend", "--prefix=true", "--tail=100"),
        "frontend-log": ("logs", "-l", "app=calfit-frontend", "--prefix=true", "--tail=100"),
    }
    for name, arguments in commands.items():
        try:
            (ARTIFACTS / f"{prefix}-{name}.txt").write_text(kube(namespace, *arguments))
        except Exception as error:
            print(f"Diagnostic collection failed: {error}", file=sys.stderr)


def promote(resources, previous, verify_new, verify_previous, on_failure=None):
    try:
        apply(LIVE, resources)
        return verify_new()
    except Exception:
        if on_failure:
            on_failure()
        if previous:
            apply(LIVE, previous)
            verify_previous()
        else:
            for item in reversed(resources):
                if item["kind"] != "Namespace":
                    kube(LIVE, "delete", item["kind"], item["metadata"]["name"], "--ignore-not-found")
        raise


def deploy(report):
    report["phase"] = "validate"
    validation = json.loads(run(sys.executable, str(ROOT / "scripts/validate_release.py"), "--github"))
    report.update(validation=validation, version=validation["version"], commit=validation["commit"])
    version, commit = report["version"], report["commit"]
    profile = os.environ.get("RELEASE_K6_PROFILE", "smoke") or "smoke"
    if profile not in ("smoke", "autoscale"):
        raise ValueError("RELEASE_K6_PROFILE must be smoke or autoscale")
    attempt = f"{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}"
    if not re.fullmatch(r"\d+-\d+", attempt):
        raise ValueError("Invalid workflow run identity")
    directory = STATE_DIR / attempt
    directory.mkdir(parents=True, exist_ok=False)
    report["retained_directory"] = str(directory)
    run("docker", "info")
    run("minikube", "-p", CONTEXT, "status")
    report["tools"] = {"minikube": run("minikube", "version"),
                       "kubectl": run("kubectl", "version", "--client"),
                       "k6": run("k6", "version")}
    run("kubectl", "--context", CONTEXT, "get", "namespace", LIVE)
    images = {}
    report["phase"] = "build_and_load_images"
    for role in ROLES:
        tag = f"calfit-{role}:{version}-{commit[:12]}-{attempt}"
        run("docker", "build", "--platform", "linux/arm64", "--build-arg", f"APP_COMMIT={commit}",
            "--file", "frontend/Dockerfile" if role == "frontend" else "Dockerfile", "--tag", tag, ".", timeout=900)
        images[role] = {"tag": tag, "docker_id": run("docker", "image", "inspect", tag, "--format", "{{.Id}}")}
    archive = directory / "images.tar"
    run("docker", "image", "save", "--output", str(archive), *(images[role]["tag"] for role in ROLES))
    run("minikube", "-p", CONTEXT, "image", "load", str(archive), timeout=600)
    for role in ROLES:
        status = json.loads(run("minikube", "-p", CONTEXT, "ssh", "--", "sudo", "crictl", "inspecti", images[role]["tag"]))["status"]
        images[role]["runtime_digests"] = runtime_digests(status)
    report["images"] = images
    candidate = f"calfit-candidate-{attempt}"
    if kube(LIVE, "get", "namespace", candidate, "--ignore-not-found", "-o", "name"):
        raise ValueError("Candidate namespace already exists; inspect rather than replacing it")
    owned = False
    report["phase"] = "candidate_verification"
    try:
        kube(LIVE, "create", "namespace", candidate)
        owned = True
        candidate_resources = render(candidate, images)
        write_json(directory / "candidate.json", {"apiVersion": "v1", "kind": "List", "items": candidate_resources})
        apply(candidate, candidate_resources)
        report["candidate"] = wait_ready(candidate, images)
        with forward(candidate, ARTIFACTS / "candidate-forward.log") as url:
            smoke(url, version, commit)
            report["candidate"]["k6"] = k6_check(candidate, url, version, commit, profile, ARTIFACTS / "k6-candidate.json")
        ready_pods(candidate, images)
    finally:
        if owned:
            collect(candidate, "candidate")
            kube(LIVE, "delete", "namespace", candidate, "--wait=true", "--timeout=180s")
    report["phase"] = "snapshot_previous_deployment"
    previous = snapshot()
    old_identity = None
    old_images = None
    if previous:
        old_state = wait_ready(LIVE)
        old_images = {role: {"tag": next(x for x in previous if x["kind"] == "Deployment" and x["metadata"]["name"] == f"calfit-{role}")["spec"]["template"]["spec"]["containers"][0]["image"],
                            "runtime_digests": sorted({p["image_digest"] for p in old_state["pods"][role]})} for role in ROLES}
        with forward(LIVE, ARTIFACTS / "previous-forward.log") as url:
            with urlopen(url + "/version", timeout=5) as response:
                old_identity = json.load(response)
            smoke(url, old_identity["version"], old_identity["commit"])
        report["previous"] = {"identity": old_identity, "images": old_images}
    write_json(directory / "previous.json", {"apiVersion": "v1", "kind": "List", "items": previous})
    resources = render(LIVE, images)
    write_json(directory / "live.json", {"apiVersion": "v1", "kind": "List", "items": resources})

    def verify_new():
        state = wait_ready(LIVE, images)
        with forward(LIVE, ARTIFACTS / "live-forward.log") as url:
            smoke(url, version, commit)
            state["k6"] = k6_check(LIVE, url, version, commit, "smoke", ARTIFACTS / "k6-live.json")
        ready_pods(LIVE, images)
        return state

    def verify_previous():
        wait_ready(LIVE, old_images)
        with forward(LIVE, ARTIFACTS / "rollback-forward.log") as url:
            smoke(url, old_identity["version"], old_identity["commit"])
        report["recovery"] = "previous_configuration_restored_and_verified"

    report["recovery"] = "not_needed"
    report["phase"] = "live_promotion"
    try:
        report["live"] = promote(resources, previous, verify_new, verify_previous,
                                 on_failure=lambda: collect(LIVE, "failed-live"))
    except Exception:
        collect(LIVE, "after-recovery")
        if report["recovery"] == "not_needed":
            report["recovery"] = "no_previous_deployment_cleanup_attempted" if not previous else "recovery_failed_or_incomplete"
        raise
    report["status"] = "verified"
    report["phase"] = "verified"
    report["attempt"] = os.environ["GITHUB_RUN_ATTEMPT"]
    report["finished_at"] = now()
    collect(LIVE, "live")
    write_json(STATE_DIR / "deployment.json", report)
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"version={version}\ncommit={commit}\nattempt={report['attempt']}\n")
        for role in ROLES:
            output.write(f"{role}_image={images[role]['tag']}\n")


def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    report = {"status": "failed", "started_at": now(), "context": CONTEXT, "namespace": LIVE,
              "operator": os.environ.get("GITHUB_ACTOR"), "rerun_operator": os.environ.get("GITHUB_TRIGGERING_ACTOR"),
              "run_id": os.environ.get("GITHUB_RUN_ID"), "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT")}
    report["workflow_url"] = (f"{os.environ.get('GITHUB_SERVER_URL', '')}/"
                              f"{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{report['run_id']}")
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with (STATE_DIR.parent / "deploy.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            deploy(report)
        return 0
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        report["traceback"] = traceback.format_exc()
        if isinstance(error, subprocess.CalledProcessError):
            report["command_error"] = error.stderr
        print(f"Kubernetes release failed: {error}", file=sys.stderr)
        traceback.print_exc()
        return 1
    finally:
        report["finished_at"] = now()
        write_json(ARTIFACTS / "release-report.json", report)


if __name__ == "__main__":
    sys.exit(main())
