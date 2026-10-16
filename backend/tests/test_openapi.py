"""OpenAPI documentation matches the API's real contract (docs only)."""

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)
SPEC = client.get("/openapi.json").json()

SCOPED = [
    ("get", "/api/itinerary"), ("post", "/api/itinerary"), ("delete", "/api/itinerary/{place_id}"),
    ("get", "/api/trips"), ("post", "/api/trips"), ("get", "/api/trips/{trip_id}"),
    ("patch", "/api/trips/{trip_id}"), ("delete", "/api/trips/{trip_id}"),
    ("put", "/api/trips/{trip_id}/days/{day_id}/order"),
    ("patch", "/api/trips/{trip_id}/activities/{activity_id}"),
    ("delete", "/api/trips/{trip_id}/activities/{activity_id}"),
    ("post", "/api/trips/{trip_id}/activities"),
    ("post", "/api/trips/{trip_id}/days/{day_id}/regenerate"),
]


def op(method, path):
    return SPEC["paths"][path][method]


def test_api_metadata():
    assert SPEC["info"]["title"] == "TripWise API"
    assert SPEC["info"]["version"] == "1.0.0"
    assert "X-Trip-ID" in SPEC["info"]["description"]


@pytest.mark.parametrize("method, path", SCOPED)
def test_trip_header_documented_as_required_uuid(method, path):
    [header] = [p for p in op(method, path)["parameters"] if p["in"] == "header"]
    assert header["name"] == "X-Trip-ID"
    assert header["required"] is True
    assert header["schema"] == {"type": "string", "format": "uuid"}
    assert "400" in header["description"]


@pytest.mark.parametrize("method, path", SCOPED)
def test_scoped_operations_document_400_and_503(method, path):
    responses = op(method, path)["responses"]
    assert {"400", "422", "503"} <= set(responses)
    assert responses["400"]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")


@pytest.mark.parametrize(
    "method, path, codes",
    [
        ("get", "/api/places", {"200", "400", "422", "502", "503", "504"}),
        ("get", "/api/geocode", {"200", "400", "422", "502", "503", "504"}),
        ("post", "/api/itinerary", {"201", "409"}),
        ("delete", "/api/itinerary/{place_id}", {"204", "404"}),
        ("post", "/api/trips", {"201", "502", "504"}),
        ("get", "/api/trips/{trip_id}", {"200", "404"}),
        ("post", "/api/trips/{trip_id}/activities", {"201", "404", "409"}),
        ("post", "/api/trips/{trip_id}/days/{day_id}/regenerate", {"200", "404", "409", "502", "504"}),
    ],
)
def test_specific_error_codes_documented(method, path, codes):
    assert codes <= set(op(method, path)["responses"])


def test_public_endpoints_have_no_trip_header():
    for method, path in (("get", "/api/places"), ("get", "/api/geocode"), ("get", "/api/planner/status"), ("get", "/health")):
        assert not [p for p in op(method, path).get("parameters", []) if p["in"] == "header"]


def test_required_query_params_documented():
    places = {p["name"]: p for p in op("get", "/api/places")["parameters"]}
    assert places["latitude"]["required"] and places["longitude"]["required"]
    assert not places["radius"].get("required")
    geocode = {p["name"]: p for p in op("get", "/api/geocode")["parameters"]}
    assert geocode["text"]["required"]


@pytest.mark.parametrize("method, path", [("get", "/api/trips"), ("get", "/api/itinerary")])
def test_runtime_unchanged_missing_header_is_still_400(method, path):
    res = getattr(client, method)(path)
    assert res.status_code == 400
    assert "X-Trip-ID" in res.json()["detail"]
