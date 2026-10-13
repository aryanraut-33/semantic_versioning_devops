"""Arithmetic examples and validation checks for both JSON and HTML responses."""

import pytest


@pytest.mark.parametrize(
    "operation,a,b,expected",
    [
        ("add", 8, 2, 10),
        ("add", -8, 2, -6),
        ("add", -8, -2, -10),
        ("add", 0, 0, 0),
        ("add", 0.1, 0.2, 0.3),
        ("subtract", 8, 2, 6),
        ("subtract", 2, 8, -6),
        ("subtract", -8, -2, -6),
        ("subtract", 0, 0, 0),
        ("subtract", 2.5, 0.75, 1.75),
        ("multiply", 8, 2, 16),
        ("multiply", -8, 2, -16),
        ("multiply", -8, -2, 16),
        ("multiply", 8, 0, 0),
        ("multiply", 1.5, 2.5, 3.75),
        ("divide", 8, 2, 4),
        ("divide", 2, 8, 0.25),
        ("divide", -8, 2, -4),
        ("divide", -8, -2, 4),
        ("divide", 0, 8, 0),
        ("divide", 7.5, 2.5, 3),
        ("divide", 1, 3, 1 / 3),
    ],
)
def test_arithmetic_results(client, operation, a, b, expected):
    response = client.get(f"/{operation}", query_string={"a": a, "b": b})

    assert response.status_code == 200
    assert response.mimetype == "application/json"
    body = response.get_json()
    assert body["operation"] == operation
    assert isinstance(body["a"], (int, float))
    assert isinstance(body["b"], (int, float))
    assert isinstance(body["result"], (int, float))
    assert body["a"] == pytest.approx(a)
    assert body["b"] == pytest.approx(b)
    assert body["result"] == pytest.approx(expected)


@pytest.mark.parametrize("operation", ["add", "subtract", "multiply", "divide"])
@pytest.mark.parametrize(
    "query",
    [
        {},
        {"a": "2"},
        {"b": "2"},
        {"a": "", "b": "2"},
        {"a": "2", "b": "   "},
        {"a": "hello", "b": "2"},
        {"a": "2", "b": "hello"},
        {"a": "nan", "b": "2"},
        {"a": "2", "b": "inf"},
        {"a": "-inf", "b": "2"},
        {"a": "1e999", "b": "2"},
        {"a": ["1", "2"], "b": "3"},
        {"a": "1", "b": ["2", "3"]},
    ],
)
def test_invalid_operands_return_bad_request(client, operation, query):
    response = client.get(f"/{operation}", query_string=query)

    assert response.status_code == 400
    assert response.mimetype == "application/json"
    body = response.get_json()
    assert isinstance(body["error"], str) and body["error"]
    assert "result" not in body


@pytest.mark.parametrize("zero", ["0", "0.0", "-0.0"])
def test_division_by_zero_is_rejected(client, zero):
    response = client.get("/divide", query_string={"a": 8, "b": zero})

    assert response.status_code == 400
    assert response.get_json() == {"error": "Cannot divide by zero."}


@pytest.mark.parametrize(
    "operation,a,b",
    [
        ("add", "1e308", "1e308"),
        ("subtract", "-1e308", "1e308"),
        ("multiply", "1e308", "1e308"),
        ("divide", "1e308", "1e-308"),
    ],
)
def test_non_finite_results_are_rejected(client, operation, a, b):
    response = client.get(f"/{operation}", query_string={"a": a, "b": b})

    assert response.status_code == 400
    assert response.get_json() == {"error": "Result is outside the supported numeric range."}


@pytest.mark.parametrize(
    "operation,expected", [("add", "10.0"), ("subtract", "6.0"), ("multiply", "16.0"), ("divide", "4.0")]
)
def test_html_form_displays_operation_result(client, operation, expected):
    response = client.get(
        f"/{operation}", query_string={"a": 8, "b": 2, "format": "html"}
    )

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert f'<output id="result">{expected}</output>' in response.get_data(as_text=True)


def test_html_form_displays_zero_result(client):
    response = client.get("/subtract?a=2&b=2&format=html")

    assert '<output id="result">0.0</output>' in response.get_data(as_text=True)


def test_html_form_displays_division_error(client):
    response = client.get("/divide?a=8&b=0&format=html")

    assert response.status_code == 400
    assert response.mimetype == "text/html"
    assert "Cannot divide by zero." in response.get_data(as_text=True)
    assert '<output id="result">' not in response.get_data(as_text=True)


def test_html_form_escapes_invalid_input(client):
    response = client.get(
        "/add", query_string={"a": "<script>alert(1)</script>", "b": 2, "format": "html"}
    )

    assert response.status_code == 400
    page = response.get_data(as_text=True)
    assert "a and b must be valid numbers." in page
    assert "<script>" not in page
    assert "&lt;script&gt;" in page
