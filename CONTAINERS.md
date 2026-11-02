# CalFit: two-container setup

Each stack runs **two containers**: frontend (Nginx serving React) and backend (Gunicorn running Flask). Node builds React but is not a running service.

Browser → localhost:5005 → frontend:80 → backend:8000

Only frontend publishes a host port. API requests stay on the same browser origin and are proxied across Docker's network. No CORS setup is needed. This is a reverse proxy with one backend, not load balancing or autoscaling.

## Local setup

These commands are for you to run. No commands, tests, or builds have been executed by the assistant. Start Docker Desktop first. Compose is included with Docker Desktop.

```bash
cd /Users/aryan/Documents/ChatGPT/semantic_versioning_devops
docker compose version
```

If frontend/package-lock.json is missing, generate it using `npm --prefix frontend install` and commit it before CI.

```bash
APP_COMMIT=local-demo docker compose --project-name calfit-local build
APP_COMMIT=local-demo docker compose --project-name calfit-local up --detach --no-build --wait --wait-timeout 90
docker compose --project-name calfit-local ps
```

Open **http://127.0.0.1:5005/**. Expect frontend and backend to be running and healthy. Compose waits for backend health before starting frontend. Use APP_PORT=5006 with the up command if 5005 is occupied.

```bash
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
python scripts/smoke_test.py --base-url http://127.0.0.1:5005 --expected-version "$(cat VERSION)" --expected-commit local-demo
curl http://127.0.0.1:5005/frontend-version.json
curl http://127.0.0.1:5005/version
docker compose --project-name calfit-local logs --tail 100 frontend backend
```

Both identity endpoints must report the same version and commit. Also check calculator modes, results, unit switching, Back/Forward, direct-link refresh, and mobile layout in a browser. Pytest covers backend logic and mocked deployment recovery; HTTP smoke tests check built assets, page routes, API proxying, and both release identities.

Stop this local stack with `docker compose --project-name calfit-local down`. After source edits, rebuild and run up again. The earlier single-image docker run commands no longer launch the full application.

## Development without Docker

Terminal 1, from the root with .venv activated:

```bash
python -m flask --app app:create_app run --host 127.0.0.1 --port 5001
```

Terminal 2:

```bash
npm --prefix frontend run dev
```

Open **http://127.0.0.1:5173/**. Vite proxies APIs to Flask on 5001. Flask is now API-only: its root returns 404. Full-stack smoke tests target Docker/Nginx, since Vite does not generate frontend-version.json.

## CI and release deployment

CI builds both images, starts a temporary Compose stack on port 5003, verifies through Nginx, and cleans up both containers. TypeScript checks run in the frontend image build.

The release script builds both images from the selected commit and captures their exact local IDs. It freezes resolved Compose settings with those IDs in manifests outside the runner checkout. A candidate stack on an automatically assigned localhost port must pass HTTP and image-ID checks before promotion.

The live project is **calfit-release**, on **http://127.0.0.1:5004/**. Promotion stops the previous stack and runs the tested pair without rebuilding or pulling. Expect brief downtime; this is not a zero-downtime rollout.

State is in `~/.local/state/semantic_versioning_devops/stack-deployment.json`. It records both image IDs, version, commit, verification time, and the current/previous manifest paths. Manifests are retained under the sibling `stacks` directory. Keep previous images and manifests for recovery.

A handled promotion failure removes the failed stack and restores and verifies the previous pair when available. The release remains failed. Forced termination or host failure can require manual recovery. GitHub Release notes record both image IDs.

During candidate verification there may be **four** running containers: two live and two temporary. Normal deployment uses two.

## One-time migration

If `release-governance-app` still runs, the release script refuses to replace live services until you migrate. First verify the new local stack on port 5005. Inspect the old container, then stop it without deleting it:

```bash
docker ps --all --filter name=release-governance-app
docker stop release-governance-app
```

Run the stop command only if this is your old deployment. Keep its image and old deployment.json. Commit the changes and trigger the release workflow. If 2.0.0 has already been published, update version metadata according to the actual latest release; do not reuse that tag.

The old single-container state is not automatically imported. On the first split deployment there is no previous pair to restore. If migration fails, inspect logs, ensure port 5004 is free, and restore the old container:

```bash
docker start release-governance-app
```

For later failures the script restores the previous pair automatically. Manual recovery uses `docker compose --project-name calfit-release --file /absolute/path/to/retained/manifest.json up --detach --no-build --pull never --wait`; select the manifest from deployment state and first stop any failed stack occupying 5004.

## References

- [Compose startup and health dependencies](https://docs.docker.com/compose/how-tos/startup-order/)
- [Nginx proxy_pass](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass)