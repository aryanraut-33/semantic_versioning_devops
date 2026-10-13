"""Shared test setup; no running server is required."""

import pytest

from app import create_app


@pytest.fixture
def app(monkeypatch):
    # A developer's exported commit must not affect the default-value tests.
    monkeypatch.delenv("APP_COMMIT", raising=False)
    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()
