from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from main import app
from places import get_http_client

FAKE_KEY = "test-key-not-real"


def feature(place_id, name, lat, lon, categories=None, formatted=None, **extra):
    props = {
        "place_id": place_id,
        "lat": lat,
        "lon": lon,
        "categories": categories or ["tourism.sights"],
        **extra,
    }
    if name is not None:
        props["name"] = name
    if formatted is not None:
        props["formatted"] = formatted
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


SAMPLE = {
    "type": "FeatureCollection",
    "features": [
        feature("p1", "eiffel Tower", 48.8584, 2.2945, formatted="Av. Gustave Eiffel, Paris"),
        feature("p2", "Arc de Triomphe", 48.8738, 2.2950, formatted="Pl. Charles de Gaulle, Paris"),
        feature("p3", None, 48.86, 2.30, address_line1="12 Rue X", address_line2="Paris"),
        feature("p4", "Louvre Museum", 48.8606, 2.3376, categories=["entertainment.museum"]),
    ],
}


@pytest.fixture
def mock_upstream(monkeypatch):
    """Route Geoapify calls to a handler; returns a list of captured requests."""
    monkeypatch.setenv("GEOAPIFY_API_KEY", FAKE_KEY)
    captured = []
    state = {"handler": lambda request: httpx.Response(200, json=SAMPLE)}

    def transport_handler(request):
        captured.append(request)
        return state["handler"](request)

    async def override_client():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(transport_handler)
        ) as client:
            yield client

    app.dependency_overrides[get_http_client] = override_client
    yield state, captured
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


PARIS = {"latitude": 48.8566, "longitude": 2.3522}


def test_health_still_works(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_returns_normalized_places(client, mock_upstream):
    res = client.get("/api/places", params={**PARIS, "radius": 3000})
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 4
    first = body["places"][0]
    assert first == {
        "id": "p1",
        "name": "eiffel Tower",
        "address": "Av. Gustave Eiffel, Paris",
        "latitude": 48.8584,
        "longitude": 2.2945,
        "categories": ["tourism.sights"],
    }
    unnamed = next(p for p in body["places"] if p["id"] == "p3")
    assert unnamed["name"] is None
    assert unnamed["address"] == "12 Rue X, Paris"


def test_builds_upstream_query(client, mock_upstream):
    _, captured = mock_upstream
    client.get(
        "/api/places",
        params={**PARIS, "radius": 1500, "categories": "Catering.Restaurant, tourism", "limit": 5},
    )
    assert len(captured) == 1
    query = parse_qs(urlparse(str(captured[0].url)).query)
    assert query["filter"] == ["circle:2.3522,48.8566,1500"]
    assert query["bias"] == ["proximity:2.3522,48.8566"]
    assert query["categories"] == ["catering.restaurant,tourism"]
    assert query["limit"] == ["5"]
    assert query["apiKey"] == [FAKE_KEY]


def test_default_category(client, mock_upstream):
    _, captured = mock_upstream
    client.get("/api/places", params=PARIS)
    query = parse_qs(urlparse(str(captured[0].url)).query)
    assert query["categories"] == ["tourism"]


def test_sort_by_name(client, mock_upstream):
    names = [p["name"] for p in client.get("/api/places", params={**PARIS, "sort": "name"}).json()["places"]]
    assert names == ["Arc de Triomphe", "eiffel Tower", "Louvre Museum", None]


def test_sort_by_name_desc(client, mock_upstream):
    names = [p["name"] for p in client.get("/api/places", params={**PARIS, "sort": "name_desc"}).json()["places"]]
    assert names == ["Louvre Museum", "eiffel Tower", "Arc de Triomphe", None]


def test_empty_results(client, mock_upstream):
    state, _ = mock_upstream
    state["handler"] = lambda r: httpx.Response(200, json={"type": "FeatureCollection", "features": []})
    res = client.get("/api/places", params=PARIS)
    assert res.status_code == 200
    assert res.json() == {"count": 0, "places": []}


def test_skips_features_without_coordinates(client, mock_upstream):
    state, _ = mock_upstream
    state["handler"] = lambda r: httpx.Response(
        200, json={"features": [{"properties": {"name": "Nowhere"}}, SAMPLE["features"][0]]}
    )
    body = client.get("/api/places", params=PARIS).json()
    assert body["count"] == 1
    assert body["places"][0]["id"] == "p1"


@pytest.mark.parametrize(
    "params",
    [
        {"longitude": 2.35},  # missing latitude
        {"latitude": 48.85},  # missing longitude
        {"latitude": 91, "longitude": 0},
        {"latitude": 0, "longitude": -181},
        {"latitude": "abc", "longitude": 0},
        {**PARIS, "radius": 0},
        {**PARIS, "radius": 50001},
        {**PARIS, "limit": 0},
        {**PARIS, "limit": 101},
        {**PARIS, "sort": "rating"},
        {**PARIS, "categories": "tourism;drop"},
        {**PARIS, "categories": "tourism..sights"},
        {**PARIS, "categories": ",".join(f"cat{i}" for i in range(21))},
    ],
)
def test_invalid_inputs_rejected(client, mock_upstream, params):
    _, captured = mock_upstream
    res = client.get("/api/places", params=params)
    assert res.status_code == 422
    assert captured == []


def test_missing_api_key(client, mock_upstream, monkeypatch):
    _, captured = mock_upstream
    monkeypatch.delenv("GEOAPIFY_API_KEY")
    res = client.get("/api/places", params=PARIS)
    assert res.status_code == 503
    assert "not configured" in res.json()["detail"]
    assert captured == []


def test_blank_api_key(client, mock_upstream, monkeypatch):
    monkeypatch.setenv("GEOAPIFY_API_KEY", "   ")
    assert client.get("/api/places", params=PARIS).status_code == 503


def test_timeout(client, mock_upstream):
    state, _ = mock_upstream

    def boom(request):
        raise httpx.ReadTimeout("timed out", request=request)

    state["handler"] = boom
    res = client.get("/api/places", params=PARIS)
    assert res.status_code == 504
    assert FAKE_KEY not in res.text


def test_connection_error(client, mock_upstream):
    state, _ = mock_upstream

    def boom(request):
        raise httpx.ConnectError("refused", request=request)

    state["handler"] = boom
    res = client.get("/api/places", params=PARIS)
    assert res.status_code == 502
    assert FAKE_KEY not in res.text


@pytest.mark.parametrize(
    "upstream_status, expected",
    [(400, 400), (401, 502), (403, 502), (429, 503), (500, 502), (503, 502)],
)
def test_upstream_errors(client, mock_upstream, upstream_status, expected):
    state, _ = mock_upstream
    state["handler"] = lambda r: httpx.Response(
        upstream_status, json={"error": "x", "message": f"bad key {FAKE_KEY}"}
    )
    res = client.get("/api/places", params=PARIS)
    assert res.status_code == expected
    assert FAKE_KEY not in res.text


@pytest.mark.parametrize(
    "payload",
    [b"not json", b"[]", b'{"features": "nope"}', b"{}"],
)
def test_malformed_upstream_body(client, mock_upstream, payload):
    state, _ = mock_upstream
    state["handler"] = lambda r: httpx.Response(200, content=payload)
    assert client.get("/api/places", params=PARIS).status_code == 502


def test_api_key_never_in_success_response(client, mock_upstream):
    res = client.get("/api/places", params=PARIS)
    assert FAKE_KEY not in res.text


# --- Regression: case- and accent-insensitive name sorting -----------------

ACCENTED = {
    "features": [
        feature("z", "Zoo de Vincennes", 1, 1),
        feature("a-grave", "À la mémoire des enfants", 1, 1),
        feature("e-acute", "Église Saint-Merry", 1, 1),
        feature("e-plain", "eiffel Tower", 1, 1),
        feature("m-acute", "Mémorial de la Shoah", 1, 1),
        feature("m-plain", "Mur des Justes", 1, 1),
        feature("o-circ", "Hôtel de Ville", 1, 1),
        feature("h-plain", "hippodrome", 1, 1),
        feature("blank", "   ", 1, 1),
        feature("none", None, 1, 1),
    ]
}


def sorted_ids(client, mock_upstream, sort):
    state, _ = mock_upstream
    state["handler"] = lambda r: httpx.Response(200, json=ACCENTED)
    body = client.get("/api/places", params={**PARIS, "sort": sort}).json()
    return [p["id"] for p in body["places"]]


def test_name_sort_ignores_accents_and_case(client, mock_upstream):
    assert sorted_ids(client, mock_upstream, "name") == [
        "a-grave",  # À la mémoire
        "e-acute",  # Église ("eg" < "ei")
        "e-plain",  # eiffel Tower
        "h-plain",  # hippodrome ("hi" < "ho")
        "o-circ",  # Hôtel de Ville
        "m-acute",  # Mémorial
        "m-plain",  # Mur
        "z",
        "blank",  # unnamed (blank/missing) stay last, in provider order
        "none",
    ]


def test_name_desc_ignores_accents_and_case(client, mock_upstream):
    assert sorted_ids(client, mock_upstream, "name_desc") == [
        "z",
        "m-plain",
        "m-acute",
        "o-circ",
        "h-plain",
        "e-plain",
        "e-acute",
        "a-grave",
        "blank",
        "none",
    ]


def test_relevance_keeps_provider_order(client, mock_upstream):
    ids = sorted_ids(client, mock_upstream, "relevance")
    assert ids == [f["properties"]["place_id"] for f in ACCENTED["features"]]


@pytest.mark.parametrize(
    "a, b",
    [
        ("apple", "Banana"),  # lowercase before uppercase-initial when earlier
        ("Église", "Eiffel"),  # É compares as E: "eg" < "ei"
        ("Ångström", "Zebra"),  # Å is not sorted after Z
        ("straße", "strasse x"),  # ß case-folds to "ss"
    ],
)
def test_name_sort_key_pairs(a, b):
    from places import name_sort_key

    assert name_sort_key(a) < name_sort_key(b)


def test_geoapify_key_never_logged(client, mock_upstream, caplog):
    """httpx logs request URLs at INFO; the Geoapify key is a URL parameter."""
    import logging

    caplog.set_level(logging.DEBUG)
    client.get("/api/places", params=PARIS)
    assert FAKE_KEY not in caplog.text
