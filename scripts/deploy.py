"""Build, verify, and deploy a pinned frontend/backend pair on Docker Desktop."""

import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
LIVE = "calfit-release"
PORT = "5004"
STATE = Path.home() / ".local/state/semantic_versioning_devops/stack-deployment.json"


def docker(*args, env=None):
    result = subprocess.run(["docker", *args], text=True, capture_output=True,
                            check=True, env=env)
    return result.stdout.strip()


def compose(manifest, project, *args):
    return docker("compose", "--project-name", project, "--file", str(manifest), *args)


def up(manifest, project):
    compose(manifest, project, "up", "--detach", "--no-build", "--pull", "never",
            "--wait", "--wait-timeout", "90")


def down(manifest, project):
    compose(manifest, project, "down", "--remove-orphans")


def logs(manifest, project):
    try:
        print(compose(manifest, project, "logs", "--no-color", "--tail", "100"), flush=True)
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"Could not retrieve logs: {error}", file=sys.stderr)


def smoke(port, version, commit):
    subprocess.run([
        sys.executable, str(ROOT / "scripts/smoke_test.py"),
        "--base-url", f"http://127.0.0.1:{port}",
        "--expected-version", version, "--expected-commit", commit,
    ], check=True)


def verify_images(manifest, project, images):
    for service, expected in images.items():
        container = compose(manifest, project, "ps", "--quiet", service)
        if not container or "\n" in container:
            raise ValueError(f"Expected exactly one running {service} container")
        actual = docker("container", "inspect", container, "--format", "{{.Image}}")
        if actual != expected:
            raise ValueError(f"{service} does not use the tested image ID")


def write_manifest(path, images, port):
    # Freeze resolved Compose settings and image IDs outside the runner checkout.
    env = {**os.environ, "APP_PORT": str(port)}
    config = json.loads(docker("compose", "--file", str(ROOT / "compose.yml"),
                               "config", "--format", "json", env=env))
    config.pop("name", None)
    config["networks"] = {"default": {}}
    for service, image in images.items():
        settings = config["services"][service]
        settings.pop("build", None)
        settings["image"] = image
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return path


def promote(manifest, images, version, commit, state_path=STATE):
    previous_record = json.loads(state_path.read_text()) if state_path.exists() else None
    previous = previous_record["current"] if previous_record else None
    existing = docker("ps", "--all", "--quiet", "--filter", f"label=com.docker.compose.project={LIVE}")
    if existing and not previous:
        raise ValueError("Live Compose project exists without deployment state; inspect before retrying.")
    legacy = docker("ps", "--quiet", "--filter", "name=^/release-governance-app$")
    if legacy:
        raise ValueError("Stop the legacy release-governance-app container first; see CONTAINERS.md.")
    if previous:
        if not Path(previous["manifest"]).is_file():
            raise ValueError("Previous deployment manifest is missing; cannot guarantee recovery.")
        verify_images(previous["manifest"], LIVE, previous["images"])
    changing = False
    try:
        changing = True
        if previous:
            down(previous["manifest"], LIVE)
        up(manifest, LIVE)
        smoke(PORT, version, commit)
        verify_images(manifest, LIVE, images)
        record = {
            "current": {"version": version, "commit": commit, "images": images,
                        "manifest": str(manifest), "project": LIVE},
            "previous": previous,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
        temporary = state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        temporary.replace(state_path)
        return record
    except Exception:
        if changing:
            logs(manifest, LIVE)
            down(manifest, LIVE)
            if previous:
                up(previous["manifest"], LIVE)
                smoke(PORT, previous["version"], previous["commit"])
                verify_images(previous["manifest"], LIVE, previous["images"])
                print("Previous image pair restored and verified; this release still failed.", flush=True)
        raise


def deploy():
    subprocess.run([sys.executable, str(ROOT / "scripts/validate_release.py"), "--github"], check=True)
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    attempt = f"{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}"
    tags = {service: f"calfit-{service}:{version}-{commit[:12]}-{attempt}"
            for service in ("frontend", "backend")}
    env = {**os.environ, "APP_COMMIT": commit,
           "FRONTEND_IMAGE": tags["frontend"], "BACKEND_IMAGE": tags["backend"]}
    docker("info")
    docker("compose", "--file", str(ROOT / "compose.yml"), "build", env=env)
    images = {service: docker("image", "inspect", tag, "--format", "{{.Id}}")
              for service, tag in tags.items()}
    directory = STATE.parent / "stacks" / attempt
    directory.mkdir(parents=True, exist_ok=False)
    candidate = write_manifest(directory / "candidate.json", images, "0")
    project = f"calfit-candidate-{attempt}"
    try:
        up(candidate, project)
        port = compose(candidate, project, "port", "frontend", "80").rsplit(":", 1)[-1]
        smoke(port, version, commit)
        verify_images(candidate, project, images)
    finally:
        logs(candidate, project)
        down(candidate, project)
    manifest = write_manifest(directory / "live.json", images, PORT)
    record = promote(manifest, images, version, commit)
    print(json.dumps(record, indent=2), flush=True)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"version={version}\ncommit={commit}\n")
        output.write(f"frontend_image={images['frontend']}\nbackend_image={images['backend']}\n")
        output.write(f"attempt={os.environ['GITHUB_RUN_ATTEMPT']}\n")


def main():
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        with (STATE.parent / "deploy.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            deploy()
        return 0
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f"Deployment failed: {error}", file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
