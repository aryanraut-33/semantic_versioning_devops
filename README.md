# Semantic Versioning and Audit-Focused Release Governance

A small Flask API for demonstrating a controlled, traceable software release process. Follow [PROJECT_PLAN.md](PROJECT_PLAN.md) for sprint scope and progress.

Sprint 1 files are prepared. Dependency installation, runtime verification, committing, and GitHub publication must be performed by the developer. No terminal commands or application tests have been run by the assistant.

## Files

| File               | Purpose                                                       |
| ------------------ | ------------------------------------------------------------- |
| `app.py`           | Application factory and three API endpoints                   |
| `VERSION`          | Application version, initially `1.0.0`                        |
| `requirements.txt` | Flask dependency                                              |
| `API_CONTRACT.md`  | Endpoint behavior and compatibility rules                     |
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

macOS includes `curl`. Flask is installed inside the project's virtual environment in the next step. Docker and the deployment VM are introduced in later sprints.

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
curl -i http://127.0.0.1:5001/health
curl -i http://127.0.0.1:5001/version
```

Each response should show HTTP `200` and `Content-Type: application/json`. Expected bodies, ignoring field order and whitespace:

| Endpoint   | Expected body                                                       |
| ---------- | ------------------------------------------------------------------- |
| `/`        | `{"message":"Release Governance API"}`                              |
| `/health`  | `{"status":"ok"}`                                                   |
| `/version` | `{"version":"1.0.0","commit":"unknown"}` when `APP_COMMIT` is unset |

These URLs also work in a browser. Stop the server with **Ctrl+C** in its terminal. This command uses Flask's local development server; the deployment server will be configured during Docker packaging.

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
git add app.py VERSION requirements.txt .gitignore README.md API_CONTRACT.md PROJECT_PLAN.md
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

After the initial `main` branch is published, start the next sprint on a new branch, for example:

```bash
git switch main
git pull --ff-only
git switch -c sprint-2-tests-docker
```

After implementing and checking that sprint, commit the intended files, publish the branch, and open a pull request into `main`. Describe what changed and how it was verified. Review the diff and merge when the sprint's completion checks pass. GitHub Actions checks arrive in Sprint 3; they are not active yet.

## Sprint 1 completion checklist

- [ ] Python environment created and Flask installed.
- [ ] All three endpoints return the documented responses.
- [ ] Source committed and `/version` reports the matching commit ID.
- [ ] Private GitHub repository published with the `main` branch.
- [ ] API contract and branch/pull-request workflow reviewed.

Once these checks pass, update Sprint 1 in `PROJECT_PLAN.md`. Automated tests and Docker packaging follow in Sprint 2.

## Troubleshooting

| Symptom                                                                    | Next step                                                                                             |
| -------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `No module named flask`                                                    | Activate `.venv` and install `requirements.txt` using that environment's `python`                     |
| Port 5001 is already in use                                                | Use `--port 5002` and change the request URLs to match                                                |
| `commit` is `unknown`                                                      | Make the initial commit, set `APP_COMMIT`, and restart the server                                     |
| Version or commit appears stale                                            | Restart after updating the file or environment variable                                               |
| Python installer encounters certificate errors during package installation | Run the installer's `Install Certificates.command` from its Python folder in Applications, then retry |

Flask setup is based on its [installation documentation](https://flask.palletsprojects.com/en/stable/installation/). The selected Flask version is listed in the official [release notes](https://flask.palletsprojects.com/en/stable/changes/#version-3-1-3).
