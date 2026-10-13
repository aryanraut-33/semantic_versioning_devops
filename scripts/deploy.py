"""Build, smoke-test, and deploy one exact image using Docker Desktop on macOS."""

import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
LIVE = "release-governance-app"
PORT = "5004"
LABEL = "release-governance.managed"
STATE = Path.home() / ".local/state/semantic_versioning_devops/deployment.json"


def docker(*args):
    result = subprocess.run(["docker", *args], text=True, capture_output=True, check=True)
    return result.stdout.strip()


def inspect_container(name):
    names = docker("container", "ls", "--all", "--format", "{{.Names}}").splitlines()
    return json.loads(docker("container", "inspect", name))[0] if name in names else None


def show_logs(name):
    # Log retrieval must not prevent container cleanup or recovery.
    try:
        result = subprocess.run(["docker", "logs", name], text=True, capture_output=True)
        print(result.stdout + result.stderr, flush=True)
    except OSError as error:
        print(f"Could not retrieve container logs: {error}", file=sys.stderr)


def smoke(port, version, commit):
    subprocess.run([
        sys.executable, str(ROOT / "scripts/smoke_test.py"),
        "--base-url", f"http://127.0.0.1:{port}",
        "--expected-version", version, "--expected-commit", commit,
    ], check=True)


def identity(container):
    labels = container["Config"].get("Labels") or {}
    if labels.get(LABEL) != "true":
        raise ValueError(f"Existing {LIVE} is unmanaged; inspect it before proceeding.")
    return {"image_id": container["Image"], "version": labels["release-governance.version"],
            "commit": labels["release-governance.commit"]}


def start(name, image, port, version, commit, restart="no"):
    docker("run", "--detach", "--name", name, "--restart", restart,
           "--label", f"{LABEL}=true", "--label", f"release-governance.version={version}",
           "--label", f"release-governance.commit={commit}",
           "--publish", f"127.0.0.1:{port}:8000", image)


def promote(image, version, commit, attempt, state_path=STATE):
    old = inspect_container(LIVE)
    previous = identity(old) if old else None
    if old and not old["State"]["Running"]:
        raise ValueError(f"Existing {LIVE} is stopped; resolve its state before deployment.")
    backup = f"{LIVE}-backup-{attempt}"
    moved = False
    replacing = False
    try:
        if old:
            docker("stop", LIVE)
            docker("rename", LIVE, backup)
            moved = True
            previous["container"] = backup
        replacing = True
        start(LIVE, image, PORT, version, commit, restart="unless-stopped")
        smoke(PORT, version, commit)
        actual = inspect_container(LIVE)
        if actual["Image"] != image:
            raise ValueError("Live container does not use the tested image ID.")
        record = {"current": {"version": version, "commit": commit, "image_id": image,
                              "container": LIVE}, "previous": previous,
                  "verified_at": datetime.now(timezone.utc).isoformat()}
        temporary = state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        temporary.replace(state_path)
    except Exception:
        # A handled failed replacement must not be reported as a successful release.
        if replacing and inspect_container(LIVE):
            show_logs(LIVE)
            docker("rm", "--force", LIVE)
        if old:
            if moved:
                docker("rename", backup, LIVE)
            docker("start", LIVE)
            smoke(PORT, previous["version"], previous["commit"])
            print("Previous deployment restored and verified; this release still failed.", flush=True)
        raise
    return record


def deploy():
    # CLI is intended only for the authorized workflow on the Mac runner.
    subprocess.run([sys.executable, str(ROOT / "scripts/validate_release.py"), "--github"], check=True)
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    commit = os.environ["GITHUB_SHA"]
    attempt = f"{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}"
    candidate = f"release-api-candidate-{attempt}"
    image_tag = f"release-governance-api:{version}-{commit[:12]}-{attempt}"
    docker("info")
    docker("build", "--build-arg", f"APP_COMMIT={commit}", "--tag", image_tag, str(ROOT))
    image = docker("image", "inspect", image_tag, "--format", "{{.Id}}")
    print(f"Built {image_tag}: {image}", flush=True)
    try:
        start(candidate, image, "", version, commit)
        candidate_info = inspect_container(candidate)
        port = candidate_info["NetworkSettings"]["Ports"]["8000/tcp"][0]["HostPort"]
        smoke(port, version, commit)
    finally:
        if inspect_container(candidate):
            show_logs(candidate)
            docker("rm", "--force", candidate)
    # Only an already-tested image ID reaches replacement of the live container.
    record = promote(image, version, commit, attempt)
    print(json.dumps(record, indent=2), flush=True)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"version={version}\ncommit={commit}\nimage_id={image}\nattempt={os.environ['GITHUB_RUN_ATTEMPT']}\n")


def main():
    try:
        # Keep state outside the runner checkout and the developer's working tree.
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
