from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from main import app
from places import get_http_client

FAKE_KEY = "test-geocode-key-not-real"


def result(place_id, name, lat, lon, confidence, formatted=None, result_type="city", **extra):
    data = {
        "place_id": place_id,
        "lat": lat,
        "lon": lon,
        "formatted": formatted or name,
        "address_line1": name,
        "result_type": result_type,
        "rank": {"confidence": confidence},
        **extra,
    }
    return data


LISBON = {"results": [result("lis", "Lisbon", 38.7077, -9.1365, 1.0, "Lisbon, Portugal", country="Portugal")]}
PARIS = {
    "results": [
        result("par-fr", "Paris", 48.8589, 2.3200, 1.0, "Paris, Ile-de-France, France", country="France"),
        result("par-tx", "Paris", 33.6609, -95.5555, 1.0, "Paris, TX, United States of America", country="United States"),
        result("par-tn", "Paris", 36.3020, -88.3267, 0.95, "Paris, TN, United States of America", country="United States"),
    ]
}


@pytest.fixture
def mock_upstream(monkeypatch):
    monkeypatch.setenv("GEOAPIFY_API_KEY", FAKE_KEY)
    captured = []
    state = {"handler": lambda request: httpx.Response(200, json=LISBON)}

    def transport_handler(request):
        captured.append(request)
        return state["handler"](request)

    async def override_client():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport_handler)) as client:
            yield client

    app.dependency_overrides[get_http_client] = override_client
    yield state, captured
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


def respond(state, payload, status=200):
    state["handler"] = lambda r: httpx.Response(status, json=payload)


# --- success -------------------------------------------------------------


def test_single_confident_match(client, mock_upstream):
    res = client.get("/api/geocode", params={"text": "Lisbon"})
    assert res.status_code == 200
    assert res.json() == {
        "query": "Lisbon",
        "count": 1,
        "confident": True,
        "results": [
            {
                "id": "lis",
                "name": "Lisbon",
                "address": "Lisbon, Portugal",
                "latitude": 38.7077,
                "longitude": -9.1365,
                "type": "city",
                "country": "Portugal",
                "confidence": 1.0,
            }
        ],
    }


def test_builds_upstream_query(client, mock_upstream):
    _, captured = mock_upstream
    client.get("/api/geocode", params={"text": "  New   York  ", "limit": 3})
    assert len(captured) == 1
    url = urlparse(str(captured[0].url))
    assert url.path == "/v1/geocode/search"
    query = parse_qs(url.query)
    assert query["text"] == ["New York"]  # whitespace collapsed
    assert query["format"] == ["json"]
    assert query["limit"] == ["3"]
    assert query["apiKey"] == [FAKE_KEY]


def test_ambiguous_results_are_not_confident(client, mock_upstream):
    state, _ = mock_upstream
    respond(state, PARIS)
    body = client.get("/api/geocode", params={"text": "Paris"}).json()
    assert body["count"] == 3
    assert body["confident"] is False
    assert [r["id"] for r in body["results"]] == ["par-fr", "par-tx", "par-tn"]


def test_single_low_confidence_match_is_not_confident(client, mock_upstream):
    state, _ = mock_upstream
    respond(state, {"results": [result("x", "Springfeld", 1, 2, 0.4)]})
    body = client.get("/api/geocode", params={"text": "Springfeld"}).json()
    assert body["count"] == 1
    assert body["confident"] is False


def test_strong_match_with_weak_runner_up_is_confident(client, mock_upstream):
    state, _ = mock_upstream
    respond(state, {"results": [result("a", "Kyoto", 35.0, 135.7, 1.0), result("b", "Kyoto St", 1, 1, 0.3)]})
    assert client.get("/api/geocode", params={"text": "Kyoto"}).json()["confident"] is True


def test_missing_confidence_is_not_confident(client, mock_upstream):
    state, _ = mock_upstream
    item = result("a", "Somewhere", 1, 2, 1.0)
    del item["rank"]
    respond(state, {"results": [item]})
    body = client.get("/api/geocode", params={"text": "Somewhere"}).json()
    assert body["results"][0]["confidence"] is None
    assert body["confident"] is False


def test_skips_invalid_and_duplicate_results(client, mock_upstream):
    state, _ = mock_upstream
    lisbon = LISBON["results"][0]
    respond(
        state,
        {
            "results": [
                lisbon,
                dict(lisbon),  # exact duplicate
                {"formatted": "No coordinates"},
                {"lat": 1, "lon": 2},  # no name at all
                "not-a-dict",
            ]
        },
    )
    body = client.get("/api/geocode", params={"text": "Lisbon"}).json()
    assert body["count"] == 1


def test_name_falls_back_to_formatted(client, mock_upstream):
    state, _ = mock_upstream
    respond(state, {"results": [{"lat": 1, "lon": 2, "formatted": "Somewhere, Earth", "rank": {"confidence": 1}}]})
    assert client.get("/api/geocode", params={"text": "somewhere"}).json()["results"][0]["name"] == "Somewhere, Earth"


# --- no matches -----------------------------------------------------------


def test_no_matches(client, mock_upstream):
    state, _ = mock_upstream
    respond(state, {"results": []})
    res = client.get("/api/geocode", params={"text": "Qzxwvut"})
    assert res.status_code == 200
    assert res.json() == {"query": "Qzxwvut", "count": 0, "confident": False, "results": []}


# --- invalid input ---------------------------------------------------------


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"text": ""},
        {"text": "   "},
        {"text": "a"},
        {"text": " a "},
        {"text": "x" * 201},
        {"text": "Lisbon", "limit": 0},
        {"text": "Lisbon", "limit": 11},
        {"text": "Lisbon", "limit": "many"},
    ],
)
def test_invalid_input_rejected(client, mock_upstream, params):
    _, captured = mock_upstream
    res = client.get("/api/geocode", params=params)
    assert res.status_code == 422
    assert captured == []


def test_short_query_message(client, mock_upstream):
    res = client.get("/api/geocode", params={"text": " a "})
    assert "at least 2 characters" in res.json()["detail"]


# --- configuration and upstream failures --------------------------------


def test_missing_api_key(client, mock_upstream, monkeypatch):
    _, captured = mock_upstream
    monkeypatch.delenv("GEOAPIFY_API_KEY")
    res = client.get("/api/geocode", params={"text": "Lisbon"})
    assert res.status_code == 503
    assert "not configured" in res.json()["detail"]
    assert captured == []


def test_timeout(client, mock_upstream):
    state, _ = mock_upstream

    def boom(request):
        raise httpx.ReadTimeout("timed out", request=request)

    state["handler"] = boom
    res = client.get("/api/geocode", params={"text": "Lisbon"})
    assert res.status_code == 504
    assert "timed out" in res.json()["detail"]
    assert FAKE_KEY not in res.text


def test_connection_error(client, mock_upstream):
    state, _ = mock_upstream

    def boom(request):
        raise httpx.ConnectError("refused", request=request)

    state["handler"] = boom
    res = client.get("/api/geocode", params={"text": "Lisbon"})
    assert res.status_code == 502
    assert FAKE_KEY not in res.text


@pytest.mark.parametrize(
    "upstream_status, expected",
    [(400, 400), (401, 502), (403, 502), (429, 503), (500, 502), (503, 502)],
)
def test_upstream_errors(client, mock_upstream, upstream_status, expected):
    state, _ = mock_upstream
    respond(state, {"error": "x", "message": f"bad key {FAKE_KEY}"}, status=upstream_status)
    res = client.get("/api/geocode", params={"text": "Lisbon"})
    assert res.status_code == expected
    assert FAKE_KEY not in res.text


@pytest.mark.parametrize("payload", [b"not json", b"[]", b'{"results": "nope"}', b"{}"])
def test_malformed_upstream_body(client, mock_upstream, payload):
    state, _ = mock_upstream
    state["handler"] = lambda r: httpx.Response(200, content=payload)
    assert client.get("/api/geocode", params={"text": "Lisbon"}).status_code == 502


def test_key_never_in_success_response(client, mock_upstream):
    assert FAKE_KEY not in client.get("/api/geocode", params={"text": "Lisbon"}).text
