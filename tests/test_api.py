"""Checks for the public behavior documented in API_CONTRACT.md."""

from pathlib import Path

import pytest

from app import create_app


def test_homepage_returns_calculator_form(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    page = response.get_data(as_text=True)
    assert "<h1>Arithmetic Calculator</h1>" in page
    assert 'name="a"' in page and 'name="b"' in page
    assert 'name="format" value="html"' in page
    for endpoint in ("add", "subtract", "multiply", "divide"):
        assert f'formaction="/{endpoint}"' in page


def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.mimetype == "application/json"
    assert response.get_json()["status"] == "ok"


def test_version_matches_version_file_and_defaults_commit(client):
    expected_version = (
        Path(__file__).resolve().parents[1] / "VERSION"
    ).read_text(encoding="utf-8").strip()
    response = client.get("/version")

    assert response.status_code == 200
    assert response.mimetype == "application/json"
    assert expected_version
    assert response.get_json()["version"] == expected_version
    assert response.get_json()["commit"] == "unknown"


def test_version_reports_supplied_commit(monkeypatch):
    commit = "a" * 40
    monkeypatch.setenv("APP_COMMIT", commit)
    client = create_app().test_client()

    assert client.get("/version").get_json()["commit"] == commit


@pytest.mark.parametrize("commit", ["", "   "])
def test_blank_commit_uses_unknown(monkeypatch, commit):
    monkeypatch.setenv("APP_COMMIT", commit)
    client = create_app().test_client()

    assert client.get("/version").get_json()["commit"] == "unknown"


def test_commit_identity_is_loaded_at_startup(monkeypatch):
    original_commit = "a" * 40
    monkeypatch.setenv("APP_COMMIT", original_commit)
    client = create_app().test_client()
    monkeypatch.setenv("APP_COMMIT", "b" * 40)

    assert client.get("/version").get_json()["commit"] == original_commit


def test_unknown_path_returns_not_found(client):
    assert client.get("/does-not-exist").status_code == 404


@pytest.mark.parametrize(
    "endpoint", ["/", "/add", "/subtract", "/multiply", "/divide", "/health", "/version"]
)
def test_post_is_not_allowed(client, endpoint):
    assert client.post(endpoint, json={}).status_code == 405
