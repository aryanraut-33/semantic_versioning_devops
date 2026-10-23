# Semantic Versioning and Audit-Focused Release Governance

A small Flask arithmetic calculator for demonstrating a controlled, traceable software release process. The local `PROJECT_PLAN.md` records sprint scope and progress.

The developer has confirmed successful Sprint 4 release validation. Sprint 5 deployment files now target the developer's Apple Silicon Mac with Docker Desktop; follow [SPRINT_5.md](SPRINT_5.md) to register the runner and deploy. The assistant has not run terminal commands, tests, or workflows. Earlier sprint guides retain historical setup instructions.

## Files

| File               | Purpose                                                       |
| ------------------ | ------------------------------------------------------------- |
| `app.py`           | Calculator operations, input validation, health, and version  |
| `templates/calculator.html` | Plain HTML calculator with four operation buttons    |
| `VERSION`          | Application version, initially `1.0.0`                        |
| `requirements.txt` | Flask and Gunicorn runtime dependencies                       |
| `requirements-dev.txt` | Runtime dependencies plus pytest                          |
| `pytest.ini`, `tests/` | Test configuration, fixtures, arithmetic and API tests     |
| `Dockerfile`, `.dockerignore` | Container packaging and build context              |
| `scripts/smoke_test.py` | HTTP verification of the packaged API                     |
| `SPRINT_2.md` | Step-by-step testing and Docker guide                               |
| `.github/workflows/ci.yml` | GitHub Actions tests, image build, and container verification |
| `SPRINT_3.md` | GitHub setup and passing/failing CI demonstration guide             |
| `API_CONTRACT.md`  | Endpoint behavior and compatibility rules                     |
| `release.json`, `CHANGELOG.md` | Declared change type and version-specific changes |
| `scripts/validate_release.py` | Version, release tag, changelog, and operator checks |
| `.github/workflows/release.yml` | Automatic release after successful main push CI, with manual fallback |
| `RELEASE_POLICY.md`, `SPRINT_4.md` | Release rules and setup instructions |
| `scripts/deploy.py`, `tests/test_deployment.py` | Exact-image deployment, verification, and failure recovery tests |
| `SPRINT_5.md` | Mac runner setup, Docker Desktop deployment, and browser demonstration |
| `.gitignore`       | Excludes local environments, generated files, and credentials |

## 1. Check or install tools on macOS

Open Terminal and check:

```bash
python3 --version
git --version
curl --version
```

Use Python 3.12 or newer for this project. If needed, download a stable Python 3 macOS installer from [Python.org](https://www.python.org/downloads/macos/), run the installer, reopen Terminal, and check the version again. Avoid preview releases for this project.

If Git is missing, install Apple's command-line developer tools, finish the installation dialog, and then run `git --version` again:

```bash
xcode-select --install
```

macOS includes `curl`. Runtime dependencies are installed inside the project's virtual environment in the next step. See `SPRINT_2.md` for Docker Desktop setup and `SPRINT_5.md` for deploying on this Mac.

## 2. Create the Python environment

Run from the project directory:

```bash
cd /Users/aryan/Documents/ChatGPT/semantic_versioning_devops
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Activate `.venv` again whenever you open a new terminal to work on the application. The `python` command then uses this environment.

## 3. Start and inspect the API

In the activated environment:

```bash
python -m flask --app app:create_app run --host 127.0.0.1 --port 5001
```

Leave this terminal running. Open another terminal and make requests:

```bash
curl -i http://127.0.0.1:5001/
curl -i "http://127.0.0.1:5001/add?a=8&b=2"
curl -i "http://127.0.0.1:5001/subtract?a=8&b=2"
curl -i "http://127.0.0.1:5001/multiply?a=8&b=2"
curl -i "http://127.0.0.1:5001/divide?a=8&b=2"
curl -i http://127.0.0.1:5001/health
curl -i http://127.0.0.1:5001/version
```

Open **http://127.0.0.1:5001/** in your browser to use the calculator. Enter A and B and click Add, Subtract, Multiply, or Divide. The page uses HTML form submissions with no JavaScript or CSS.

The entrypoint returns HTML. Operation endpoints return JSON by default; the form includes `format=html` to display results on the page. All successful responses return HTTP `200`:

| Endpoint   | Expected body                                                       |
| ---------- | ------------------------------------------------------------------- |
| `/`        | HTML calculator page                                                |
| `/add?a=8&b=2` | `{"operation":"add","a":8.0,"b":2.0,"result":10.0}`             |
| `/subtract?a=8&b=2` | Result `6.0` in the same JSON structure                     |
| `/multiply?a=8&b=2` | Result `16.0` in the same JSON structure                    |
| `/divide?a=8&b=2` | Result `4.0` in the same JSON structure                       |
| `/health`  | `{"status":"ok"}`                                                   |
| `/version` | `{"version":"1.0.0","commit":"unknown"}` when `APP_COMMIT` is unset |

These URLs also work in a browser. Stop the server with **Ctrl+C** in its terminal. This command uses Flask's local development server. The Docker image uses Gunicorn and is demonstrated on host port `5002` in `SPRINT_2.md`.

Missing or invalid operands and division by zero return HTTP `400`. Negative values and decimals are supported; floating-point results may be approximate. See [API_CONTRACT.md](API_CONTRACT.md) for response details. No additional dependency is required for the calculator UI.

## 4. Commit the foundation and identify its source

This workspace already has a `.git` directory, so initialization is not needed. Inspect the working tree first:

```bash
git status
```

If your Git author identity is not configured, set it for this repository. Replace the example values with your name and GitHub-associated email or GitHub private email:

```bash
git config user.name "YOUR_NAME"
git config user.email "YOUR_EMAIL"
```

After the manual checks pass, stage the Sprint 1 files, review the staged changes, and commit:

```bash
git add app.py templates VERSION requirements.txt .gitignore README.md API_CONTRACT.md
git diff --cached
git commit -m "feat: add Flask API foundation"
git branch -M main
```

Restart the server with the committed source identity:

```bash
export APP_COMMIT="$(git rev-parse HEAD)"
python -m flask --app app:create_app run --host 127.0.0.1 --port 5001
```

From another terminal in the project directory, compare:

```bash
git rev-parse HEAD
curl -i http://127.0.0.1:5001/version
```

The `commit` field should match the full Git commit ID. The environment variable lasts only for that terminal session. After source changes, commit again and restart with the updated value. The application does not automatically discover the commit.

`1.0.0` is the planned initial application version. The initial successful release tag will be created through the release process in a later sprint.

## 5. Publish the private GitHub repository

If you already use an authenticated GitHub client, publish this local repository with that client. Otherwise, GitHub Desktop provides a simple setup without configuring command-line authentication:

1. Create or sign in to your GitHub account.
2. Install [GitHub Desktop](https://desktop.github.com/) and sign in to GitHub.com.
3. Choose **File → Add Local Repository** and select this project directory.
4. Choose **Publish repository** and use `semantic_versioning_devops` as its name.
5. Keep **Keep this code private** selected and publish.
6. Open the repository on GitHub and verify that the files and `main` branch are present.

If the local repository is already connected to GitHub, use its existing repository and push the commit rather than creating a duplicate. The instructions follow GitHub's [local repository guide](https://docs.github.com/en/desktop/adding-and-cloning-repositories/adding-a-repository-from-your-local-computer-to-github-desktop).

## 6. Use a branch and pull request for subsequent work

With the completed Sprint 2 code checked out, start Sprint 3 on a new branch. Skip branch creation if you are already on `sprint-3-ci`:

```bash
git status --short
git switch -c sprint-3-ci
```

After implementing and checking a sprint, commit the intended files, publish the branch, and open a pull request into `main`. Describe what changed and how it was verified. Review the diff and merge when the sprint's completion checks pass. The Sprint 3 workflow runs on pull requests targeting `main` and updates to `main` once published; see `SPRINT_3.md` for setup.

## Continuous integration

The **CI** workflow runs on a GitHub-hosted Ubuntu 24.04 runner. Its **Test and verify container** job installs dependencies, runs pytest, builds the Docker image with the checked-out commit ID, and verifies the running calculator through `scripts/smoke_test.py`. Failures stop later ordinary steps. Container logs and cleanup are attempted even after a failure.

The workflow uses Python 3.12 and the Docker engine on the hosted runner. Your Mac's Docker Desktop and port assignments do not affect it. The temporary CI container is removed after verification.

## Deployment

The **Release** workflow starts automatically after **CI succeeds for a push to `main`**, including a merged pull request. It validates the exact commit that passed CI on a hosted runner, then builds and verifies the application on your Apple Silicon Mac using a self-hosted runner with labels `macOS`, `ARM64`, and `release-demo`. It tests a candidate container before deploying the same image ID as `release-governance-app` at **http://127.0.0.1:5004/**. After live HTTP verification, a hosted job creates the release tag and GitHub Release, including a link to the triggering CI run. Follow [SPRINT_5.md](SPRINT_5.md) for commands and failure recovery. Previous containers/images and `~/.local/state/semantic_versioning_devops/deployment.json` support recovery. The runner uses its own checkout, separate from your working folder. Keep Docker Desktop active and the Mac awake during deployment and demonstrations.

For the demonstration, the flow is **commit → push/open PR → CI → merge → main CI → automatic Release → GitHub Release**. Merge the automation changes into `main` to enable this behavior. PR checks and failed CI runs do not deploy. The `RELEASE_OPERATOR` checks still apply to the push/merge actor and rerun actors. You still edit `VERSION`, `release.json`, and `CHANGELOG.md`; already-released or incorrect versions fail release validation before deployment. Complete one release before merging the next demo version. **Actions → Release → Run workflow → main** remains available as a manual fallback and independently repeats validation/tests. See [RELEASE_POLICY.md](RELEASE_POLICY.md) for the full trigger and authorization rules.

## Sprint 1 completion checklist

- [ ] Python environment created and Flask installed.
- [ ] The calculator page, four operations, and health/version endpoints return the documented responses.
- [ ] Source committed and `/version` reports the matching commit ID.
- [ ] Private GitHub repository published with the `main` branch.
- [ ] API contract and branch/pull-request workflow reviewed.

Once these checks pass, update Sprint 1 in the local `PROJECT_PLAN.md`. Current development continues with [Sprint 5: deployment and verification](SPRINT_5.md).

## Troubleshooting

| Symptom                                                                    | Next step                                                                                             |
| -------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `No module named flask`                                                    | Activate `.venv` and install `requirements.txt` using that environment's `python`                     |
| Port 5001 is already in use                                                | Use `--port 5002` and change the request URLs to match                                                |
| `commit` is `unknown`                                                      | Make the initial commit, set `APP_COMMIT`, and restart the server                                     |
| Version or commit appears stale                                            | Restart after updating the file or environment variable                                               |
| Python installer encounters certificate errors during package installation | Run the installer's `Install Certificates.command` from its Python folder in Applications, then retry |

Flask setup is based on its [installation documentation](https://flask.palletsprojects.com/en/stable/installation/). The selected Flask version is listed in the official [release notes](https://flask.palletsprojects.com/en/stable/changes/#version-3-1-3).
