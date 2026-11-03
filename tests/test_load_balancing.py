"""Instance identification and distribution-check failure cases; no cluster needed."""

from collections import Counter
from email.message import Message
from io import BytesIO
import json

import pytest

from app import create_app
from scripts import check_load_balancing as checker


@pytest.mark.parametrize("path,status", [("/health", 200), ("/version", 200),
                                         ("/api/unknown", 404)])
def test_backend_identifies_its_pod_on_success_and_error(monkeypatch, path, status):
    monkeypatch.setenv("INSTANCE_ID", "calfit-backend-pod-a")
    client = create_app().test_client()
    response = client.get(path)
    assert response.status_code == status
    assert response.headers["X-Instance-ID"] == "calfit-backend-pod-a"


def test_calculation_response_has_identity_without_changing_result(monkeypatch):
    monkeypatch.setenv("INSTANCE_ID", "pod-b")
    response = create_app().test_client().post("/api/fitness", json=checker.FITNESS_INPUT)
    assert response.status_code == 200
    assert response.headers["X-Instance-ID"] == "pod-b"
    assert response.json["calories"] == checker.FITNESS_EXPECTED["calories"]


@pytest.mark.parametrize("identity", [None, "", "   "])
def test_local_identity_falls_back_to_hostname(monkeypatch, identity):
    if identity is None:
        monkeypatch.delenv("INSTANCE_ID", raising=False)
    else:
        monkeypatch.setenv("INSTANCE_ID", identity)
    monkeypatch.setattr("app.socket.gethostname", lambda: "local-host")
    assert create_app().test_client().get("/health").headers["X-Instance-ID"] == "local-host"


def test_distribution_allows_unequal_counts():
    counts = {"/version": Counter({"pod-a": 31, "pod-b": 19}),
              "/api/fitness": Counter({"pod-a": 20, "pod-b": 30})}
    checker.verify_distribution(counts, 2, ["pod-a", "pod-b"])


def test_calculation_must_reach_multiple_instances_too():
    counts = {"/version": Counter({"pod-a": 25, "pod-b": 25}),
              "/api/fitness": Counter({"pod-a": 50})}
    with pytest.raises(ValueError, match="/api/fitness"):
        checker.verify_distribution(counts, 2)


def test_unexpected_instance_is_rejected():
    with pytest.raises(ValueError, match="ready pod names"):
        checker.verify_distribution({"/version": Counter({"a": 25, "stale": 25})}, 2, ["a", "b"])


@pytest.mark.parametrize("instance,body,error", [
    ("pod-a", {"version": "wrong"}, "unexpected response"),
    (None, {"version": "2.0.0"}, "missing X-Instance-ID"),
])
def test_checker_rejects_wrong_results_or_missing_header(monkeypatch, instance, body, error):
    response = BytesIO(json.dumps(body).encode())
    response.status = 200
    response.headers = Message()
    response.headers["Content-Type"] = "application/json"
    if instance:
        response.headers["X-Instance-ID"] = instance
    monkeypatch.setattr(checker, "urlopen", lambda *a, **k: response)
    with pytest.raises(ValueError, match=error):
        checker.request_instance("http://localhost", "/version", {"version": "2.0.0"})
