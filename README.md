# CalFit — Fitness Calculator & Release Governance

React + TypeScript fitness calculator with a Flask API. Estimate adult calorie requirements, resting energy, and BMI using metric or US measurements. No login or stored measurements.

## Architecture

Browser → **frontend container: Nginx + React** → **backend container: Flask + Gunicorn**

Docker Compose runs two containers. Only frontend publishes a host port. Nginx serves pages and forwards API requests to Flask over the internal network.

**Follow [CONTAINERS.md](CONTAINERS.md)** for commands, verification, development setup, CI, and migration from the old single container.

```bash
APP_COMMIT=local-demo docker compose --project-name calfit-local build
APP_COMMIT=local-demo docker compose --project-name calfit-local up --detach --no-build --wait --wait-timeout 90
```

Open **http://127.0.0.1:5006/**. Docker Desktop must be running and frontend/package-lock.json must exist (generate with `npm --prefix frontend install` and commit it). No commands, builds, or tests have been run by the assistant.

| Component | Files |
|---|---|
| Frontend | frontend/src/main.tsx, frontend/src/styles.css |
| Frontend image and proxy | frontend/Dockerfile, frontend/nginx.conf |
| API and formulas | app.py, fitness.py |
| Backend image | Dockerfile |
| Two-container stack | compose.yml |
| Tests and HTTP verification | tests/, scripts/smoke_test.py |
| CI | .github/workflows/ci.yml |
| Kubernetes release and recovery | scripts/deploy_kubernetes.py, .github/workflows/release.yml |

## Pages and APIs

| Action | Browser path | API request |
|---|---|---|
| Home | / | None |
| Calories + BMI | /calories-bmi | POST /api/fitness on submission |
| BMI only | /bmi | POST /api/bmi on submission |
| Successful calculation | /calories-bmi/results or /bmi/results | Displays returned data |
| Behind the numbers | /behind-the-numbers | None |

Nginx serves page routes; Flask serves JSON APIs. Results are only held in React memory. Refreshing or revisiting a results page prompts recalculation. Arithmetic endpoints have been removed.

## Verification

```bash
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
python scripts/smoke_test.py --base-url http://127.0.0.1:5006 --expected-version "$(cat VERSION)" --expected-commit local-demo
```

Reference case: male coefficient, age 30, 80 kg, 180 cm, moderate activity → **1,780 resting kcal/day**, **2,759 maintenance kcal/day**, **BMI 24.69 / Healthy weight**. Test browser navigation, unit switching, and mobile layout manually too.

## Release workflow

Push/open PR → CI → merge → successful main CI → authorized Release → candidate Kubernetes namespace → verified live rollout in calfit → GitHub Release with audit/k6 assets. Manual dispatch remains available.

Follow **Phase 7 in [LOAD_BALANCING.md](LOAD_BALANCING.md)** for runner setup, version preparation, optional candidate autoscaling tests, snapshot recovery and evidence. Routine releases use short k6 smoke checks; full candidate scaling verification is configurable. Both images are built from the validated commit and checked against Minikube runtime identities.

The workflow now deploys to Kubernetes, not Compose. Open the application with the documented frontend port-forward on 5007. Compose remains available for local development. No commands, releases or tests were executed by the assistant.

## Documentation

- [Container setup](CONTAINERS.md)
- [Kubernetes setup, load balancing, CPU autoscaling, and k6 traffic generation](LOAD_BALANCING.md)
- [API contract](API_CONTRACT.md)
- [Formulas and sources](FORMULAS.md)
- [Release policy](RELEASE_POLICY.md)
- PROJECT_PLAN.md is the local development reference.
