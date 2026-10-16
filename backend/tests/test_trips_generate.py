"""API tests for POST /api/trips with generate=true (Geoapify mocked)."""

import uuid
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as SASession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, Trip, TripActivity, TripCity, TripDay, enable_sqlite_foreign_keys, get_db
from main import app
from places import get_http_client

OWNER = str(uuid.uuid4())
FAKE_KEY = "planner-test-key-not-real"
KYOTO = {"name": "Kyoto", "address": "Kyoto, Japan", "latitude": 35.0116, "longitude": 135.7681, "days": 2}
OSAKA = {"name": "Osaka", "latitude": 34.69, "longitude": 135.50, "days": 1}


def feature(pid, name, lat, lon, cats):
    return {
        "type": "Feature",
        "properties": {"place_id": pid, "name": name, "lat": lat, "lon": lon,
                       "formatted": f"{name}, Kyoto", "categories": cats},
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


def features_for(categories: str, count: int, prefix: str):
    cats = categories.split(",")
    offset = (sum(map(ord, prefix)) % 5) * 0.002  # keep interests ~200 m apart
    return [
        feature(f"{prefix}-{i}", f"{prefix.title()} {i}", 35.0 + offset + (i % 4) * 0.01,
                135.76 + (i // 4) * 0.01, [cats[0]])
        for i in range(count)
    ]


@pytest.fixture
def engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def upstream(monkeypatch):
    """Mock Geoapify. Default: 12 places per requested interest."""
    monkeypatch.setenv("GEOAPIFY_API_KEY", FAKE_KEY)
    calls = []
    state = {"per_query": 12, "handler": None}

    def default_handler(request):
        q = parse_qs(urlparse(str(request.url)).query)
        cats = q["categories"][0]
        prefix = cats.split(",")[0].split(".")[-1]
        return httpx.Response(200, json={"type": "FeatureCollection",
                                         "features": features_for(cats, state["per_query"], prefix)})

    def transport(request):
        calls.append(request)
        return (state["handler"] or default_handler)(request)

    async def override_client():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            yield client

    app.dependency_overrides[get_http_client] = override_client
    yield state, calls
    app.dependency_overrides.pop(get_http_client, None)


@pytest.fixture
def client(factory, upstream):
    def override_get_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def counts(factory):
    with factory() as s:
        return tuple(s.scalar(select(func.count()).select_from(m)) for m in (Trip, TripCity, TripDay, TripActivity))


def generate(client, **overrides):
    body = {"cities": [KYOTO], "generate": True, **overrides}
    return client.post("/api/trips", json=body, headers={"X-Trip-ID": OWNER})


# --- Success ----------------------------------------------------------------


def test_generates_single_city_trip(client, upstream, factory):
    res = generate(client, interests=["culture", "food"], pace="balanced", start_date="2026-11-03")
    assert res.status_code == 201, res.text
    trip = res.json()
    assert trip["planner"] == "auto" and trip["warnings"] == []
    assert len(trip["days"]) == 2
    for day in trip["days"]:
        assert day["generated_by"] == "auto"
        assert day["theme"] == "Culture and Food"
        assert [a["position"] for a in day["activities"]] == [0, 1, 2]
        assert [a["slot"] for a in day["activities"]] == ["morning", "afternoon", "evening"]
        for a in day["activities"]:
            assert a["source"] == "auto" and a["kind"] == "place" and a["note"] is None
            assert a["place_id"] and a["name"] and a["latitude"] and a["categories"]
    ids = [a["place_id"] for d in trip["days"] for a in d["activities"]]
    assert len(ids) == len(set(ids)) == 6
    # Persisted, and the same on a fresh read.
    again = client.get(f"/api/trips/{trip['id']}", headers={"X-Trip-ID": OWNER}).json()
    assert again["days"] == trip["days"]
    assert counts(factory) == (1, 1, 2, 6)


def test_queries_geoapify_once_per_interest_around_the_city(client, upstream):
    _, calls = upstream
    generate(client, interests=["nature", "food"])
    assert len(calls) == 2
    queries = [parse_qs(urlparse(str(c.url)).query) for c in calls]
    assert sorted(q["categories"][0] for q in queries) == ["catering.restaurant,catering.cafe", "leisure.park,natural"]
    for q in queries:
        assert q["filter"] == ["circle:135.7681,35.0116,10000"]
        assert q["apiKey"] == [FAKE_KEY]


def test_no_interests_uses_general_sightseeing(client, upstream):
    _, calls = upstream
    trip = generate(client).json()
    assert len(calls) == 1
    assert "tourism.sights" in parse_qs(urlparse(str(calls[0].url)).query)["categories"][0]
    assert trip["days"][0]["theme"] == "Sightseeing"


@pytest.mark.parametrize("pace, per_day", [("relaxed", 2), ("balanced", 3), ("packed", 5)])
def test_pace_controls_activities_per_day(client, pace, per_day):
    trip = generate(client, pace=pace).json()
    assert [len(d["activities"]) for d in trip["days"]] == [per_day, per_day]


def test_widens_radius_once_when_too_few_places(client, upstream):
    state, calls = upstream

    def handler(request):
        radius = parse_qs(urlparse(str(request.url)).query)["filter"][0].split(",")[-1]
        n = 2 if radius == "10000" else 12
        return httpx.Response(200, json={"features": features_for("tourism.sights", n, f"r{radius}")})

    state["handler"] = handler
    trip = generate(client).json()
    assert [parse_qs(urlparse(str(c.url)).query)["filter"][0].split(",")[-1] for c in calls] == ["10000", "25000"]
    assert sum(len(d["activities"]) for d in trip["days"]) == 6


def test_partial_results_generate_with_warning(client, upstream):
    state, _ = upstream
    state["per_query"] = 4  # need 6 for 2 balanced days
    res = generate(client)
    assert res.status_code == 201
    trip = res.json()
    assert sorted(len(d["activities"]) for d in trip["days"]) == [2, 2]
    assert "Only 4" in trip["warnings"][0]


def test_generate_false_keeps_empty_days(client, upstream):
    _, calls = upstream
    res = client.post("/api/trips", json={"cities": [KYOTO]}, headers={"X-Trip-ID": OWNER})
    assert res.status_code == 201
    assert all(d["activities"] == [] and d["generated_by"] is None for d in res.json()["days"])
    assert calls == []


def test_unnamed_and_duplicate_places_are_skipped(client, upstream):
    state, _ = upstream
    good = [feature(f"g{i}", f"Spot {i}", 35.0 + i * 0.01, 135.76, ["tourism.sights"]) for i in range(6)]
    junk = [
        feature("n1", None, 35.0, 135.76, ["tourism.sights"]),
        feature("n2", "  ", 35.0, 135.76, ["tourism.sights"]),
        good[0],
        feature("other-id", "Spot 0", 35.0, 135.76, ["tourism.sights"]),
    ]
    state["handler"] = lambda r: httpx.Response(200, json={"features": junk + good})
    trip = generate(client).json()
    names = [a["name"] for d in trip["days"] for a in d["activities"]]
    assert sorted(names) == sorted(f"Spot {i}" for i in range(6))


# --- Validation (nothing fetched, nothing saved) ---------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"cities": [KYOTO, OSAKA], "planner": "ai"},  # AI is single-city only
        {"interests": ["skydiving"]},
        {"pace": "turbo"},
        {"generate": "please"},
    ],
)
def test_invalid_generation_requests(client, upstream, factory, overrides):
    _, calls = upstream
    res = generate(client, **overrides)
    assert res.status_code == 422
    assert calls == [] and counts(factory) == (0, 0, 0, 0)


def test_multi_city_without_generation_still_allowed(client):
    res = client.post("/api/trips", json={"cities": [KYOTO, OSAKA]}, headers={"X-Trip-ID": OWNER})
    assert res.status_code == 201


def test_entertainment_interest_accepted(client, upstream):
    _, calls = upstream
    assert generate(client, interests=["entertainment"]).status_code == 201
    assert "entertainment.zoo" in parse_qs(urlparse(str(calls[0].url)).query)["categories"][0]


# --- Failures leave nothing behind --------------------------------------------


def test_empty_results(client, upstream, factory):
    state, _ = upstream
    state["handler"] = lambda r: httpx.Response(200, json={"features": []})
    res = generate(client)
    assert res.status_code == 422
    assert "Not enough places found near Kyoto" in res.json()["detail"]
    assert counts(factory) == (0, 0, 0, 0)


def test_fewer_places_than_days(client, upstream, factory):
    state, _ = upstream
    state["per_query"] = 1
    res = generate(client)  # 2 days, 1 place
    assert res.status_code == 422 and "found 1" in res.json()["detail"]
    assert counts(factory) == (0, 0, 0, 0)


@pytest.mark.parametrize(
    "status, expected",
    [(500, 502), (401, 502), (429, 503), (400, 400)],
)
def test_upstream_http_errors(client, upstream, factory, status, expected):
    state, _ = upstream
    state["handler"] = lambda r: httpx.Response(status, json={"message": f"key {FAKE_KEY}"})
    res = generate(client)
    assert res.status_code == expected
    assert res.json()["detail"].startswith("Could not generate the itinerary.")
    assert FAKE_KEY not in res.text
    assert counts(factory) == (0, 0, 0, 0)


@pytest.mark.parametrize("exc", [httpx.ReadTimeout, httpx.ConnectError])
def test_upstream_network_errors(client, upstream, factory, exc):
    state, _ = upstream

    def boom(request):
        raise exc("down", request=request)

    state["handler"] = boom
    res = generate(client)
    assert res.status_code in (502, 504)
    assert counts(factory) == (0, 0, 0, 0)


def test_one_failing_interest_fails_the_whole_generation(client, upstream, factory):
    state, _ = upstream

    def handler(request):
        cats = parse_qs(urlparse(str(request.url)).query)["categories"][0]
        if cats.startswith("catering"):
            return httpx.Response(500)
        return httpx.Response(200, json={"features": features_for(cats, 12, "ok")})

    state["handler"] = handler
    assert generate(client, interests=["culture", "food"]).status_code == 502
    assert counts(factory) == (0, 0, 0, 0)


def test_missing_api_key(client, upstream, factory, monkeypatch):
    _, calls = upstream
    monkeypatch.delenv("GEOAPIFY_API_KEY")
    res = generate(client)
    assert res.status_code == 503
    assert calls == [] and counts(factory) == (0, 0, 0, 0)


def test_database_failure_rolls_back_everything(client, factory, monkeypatch):
    """Plan succeeds, then the write fails mid-transaction: no rows remain."""
    existing = client.post("/api/trips", json={"cities": [OSAKA]}, headers={"X-Trip-ID": OWNER}).json()
    original_flush = SASession.flush

    def failing_flush(self, *args, **kwargs):
        if any(isinstance(o, TripActivity) for o in self.new):
            raise OperationalError("INSERT", {}, Exception("simulated outage"))
        return original_flush(self, *args, **kwargs)

    monkeypatch.setattr(SASession, "flush", failing_flush)
    res = generate(client)
    monkeypatch.setattr(SASession, "flush", original_flush)
    assert res.status_code == 503
    assert res.json()["detail"] == "Trip storage is unavailable."
    # Only the earlier, unrelated trip is left, untouched.
    assert counts(factory) == (1, 1, 1, 0)
    assert client.get(f"/api/trips/{existing['id']}", headers={"X-Trip-ID": OWNER}).json()["days"] == existing["days"]


def test_generated_trip_cascades_on_delete(client, factory):
    trip = generate(client).json()
    assert counts(factory) == (1, 1, 2, 6)
    assert client.delete(f"/api/trips/{trip['id']}", headers={"X-Trip-ID": OWNER}).status_code == 204
    assert counts(factory) == (0, 0, 0, 0)


def test_http_client_not_ready_returns_503(factory, monkeypatch):
    """Without app startup (no shared HTTP client) generation fails cleanly."""
    monkeypatch.setenv("GEOAPIFY_API_KEY", FAKE_KEY)

    def override_get_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        res = TestClient(app).post(
            "/api/trips", json={"cities": [KYOTO], "generate": True}, headers={"X-Trip-ID": OWNER}
        )
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 503 and "not ready" in res.json()["detail"]
    assert counts(factory) == (0, 0, 0, 0)
