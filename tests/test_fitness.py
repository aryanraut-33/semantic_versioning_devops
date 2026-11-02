"""Formula reference cases, unit equivalence, boundaries, and API validation."""

import pytest

from fitness import ACTIVITIES, bmi_category

BASE = {"units": "metric", "age": 30, "weight": 80, "height": 180,
        "sex": "male", "activity": "moderate"}


def test_combined_reference_case(client):
    response = client.post("/api/fitness", json=BASE)
    assert response.status_code == 200
    assert response.json == {
        "measurements": {"weight_kg": 80, "height_cm": 180},
        "bmi": {"value": 24.69, "category": "Healthy weight"},
        "calories": {"resting_kcal": 1780, "maintenance_kcal": 2759,
                     "activity": "moderate", "activity_factor": 1.55,
                     "formula": "Mifflin–St Jeor"},
    }


def test_female_coefficient(client):
    response = client.post("/api/calories", json={**BASE, "sex": "female"})
    assert response.status_code == 200
    assert response.json["calories"]["resting_kcal"] == 1614
    assert response.json["calories"]["maintenance_kcal"] == 2502
    assert "bmi" not in response.json


def test_us_and_metric_are_equivalent(client):
    metric = client.post("/api/fitness", json=BASE).json
    us = client.post("/api/fitness", json={**BASE, "units": "us",
        "weight": 80 / 0.45359237, "height": 180 / 2.54}).json
    assert us == metric


def test_bmi_only_does_not_require_sex_or_activity(client):
    response = client.post("/api/bmi", json={"units": "us", "age": 35,
        "height": 70, "weight": 154.3235835294143})
    assert response.status_code == 200
    assert response.json["bmi"]["value"] == 22.14
    assert "calories" not in response.json


@pytest.mark.parametrize("activity,factor", [(key, value[1]) for key, value in ACTIVITIES.items()])
def test_activity_levels(client, activity, factor):
    response = client.post("/api/calories", json={**BASE, "activity": activity})
    assert response.status_code == 200
    assert response.json["calories"]["activity_factor"] == factor
    expected = None if activity == "resting" else round(1780 * factor)
    assert response.json["calories"]["maintenance_kcal"] == expected


@pytest.mark.parametrize("value,category", [
    (18.4999, "Underweight"), (18.5, "Healthy weight"), (24.9999, "Healthy weight"),
    (25, "Overweight"), (29.9999, "Overweight"), (30, "Obesity"),
])
def test_bmi_category_boundaries(value, category):
    assert bmi_category(value) == category


def test_classification_uses_unrounded_bmi(client):
    response = client.post("/api/bmi", json={"units": "metric", "age": 30,
        "height": 200, "weight": 99.9996})
    assert response.json["bmi"] == {"value": 25.0, "category": "Healthy weight"}


@pytest.mark.parametrize("field,value", [
    ("age", 19), ("age", 101), ("age", 30.5), ("age", True), ("age", "30"),
    ("height", 0), ("height", 251), ("weight", -1), ("weight", 351),
    ("weight", None), ("height", "180"), ("units", "imperial"),
    ("sex", "unknown"), ("sex", []), ("activity", "unknown"), ("activity", []),
    ("weight", float("nan")), ("height", float("inf")), ("age", 10**400),
])
def test_invalid_fields(client, field, value):
    response = client.post("/api/fitness", json={**BASE, field: value})
    assert response.status_code == 400
    assert response.json["field"] == field
    assert "error" in response.json


@pytest.mark.parametrize("field", list(BASE))
def test_missing_fields(client, field):
    payload = {key: value for key, value in BASE.items() if key != field}
    assert client.post("/api/fitness", json=payload).status_code == 400


@pytest.mark.parametrize("payload", [[], "text", 7, {}, {**BASE, "extra": 1}])
def test_invalid_objects(client, payload):
    assert client.post("/api/fitness", json=payload).status_code == 400


def test_json_and_method_errors(client):
    assert client.post("/api/fitness", data="null", content_type="application/json").status_code == 400
    malformed = client.post("/api/fitness", data="{", content_type="application/json")
    assert malformed.status_code == 400 and malformed.is_json
    assert client.post("/api/fitness", data="{}").status_code == 415
    assert client.get("/api/fitness").status_code == 405
    assert client.get("/api/unknown").status_code == 404
    oversized = client.post("/api/fitness", data=" " * 17000, content_type="application/json")
    assert oversized.status_code == 413


def test_activity_options_match_calculation_options(client):
    response = client.get("/api/activities")
    assert response.status_code == 200
    assert {item["id"] for item in response.json["activities"]} == set(ACTIVITIES)


@pytest.mark.parametrize("age", [20, 100])
def test_supported_age_boundaries(client, age):
    assert client.post("/api/fitness", json={**BASE, "age": age}).status_code == 200
