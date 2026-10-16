"""Multi-city automatic planning (Geoapify mocked; AI not involved)."""

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
from trips import allocate_days

A = str(uuid.uuid4())
B = str(uuid.uuid4())
KEY = "multi-test-key-not-real"
KYOTO = {"name": "Kyoto", "address": "Kyoto, Japan", "latitude": 35.0116, "longitude": 135.7681}
OSAKA = {"name": "Osaka", "address": "Osaka, Japan", "latitude": 34.6937, "longitude": 135.5023}
NARA = {"name": "Nara", "address": "Nara, Japan", "latitude": 34.6851, "longitude": 135.8048}


def features_around(lat, lon, prefix, n=12):
    return [{"properties": {"place_id": f"{prefix}-{i}", "name": f"{prefix} spot {i}",
                            "lat": lat + (i % 4) * 0.004, "lon": lon + (i // 4) * 0.004,
                            "formatted": f"{prefix} spot {i}", "categories": ["tourism.sights"]},
             "geometry": {"coordinates": [lon + (i // 4) * 0.004, lat + (i % 4) * 0.004]}} for i in range(n)]


@pytest.fixture
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def geo(monkeypatch):
    """Places around whatever centre is requested; per-city overrides by name."""
    monkeypatch.setenv("GEOAPIFY_API_KEY", KEY)
    state = {"calls": [], "override": {}, "shared_ids": False}

    def transport(request):
        if request.url.host != "api.geoapify.com":
            raise AssertionError(f"unexpected host {request.url.host}")
        q = parse_qs(urlparse(str(request.url)).query)
        lon, lat, radius = (float(x) for x in q["filter"][0].removeprefix("circle:").split(","))
        state["calls"].append((round(lat, 4), round(lon, 4), int(radius)))
        for city_lat, handler in state["override"].items():
            if abs(lat - city_lat) < 1e-6:
                return handler(request)
        prefix = "shared" if state["shared_ids"] else f"c{lat:.2f}"
        return httpx.Response(200, json={"features": features_around(lat, lon, prefix)})

    async def override():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as c:
            yield c

    app.dependency_overrides[get_http_client] = override
    yield state
    app.dependency_overrides.pop(get_http_client, None)


@pytest.fixture
def client(factory, geo):
    def override_get_db():
        with factory() as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def h(owner=A):
    return {"X-Trip-ID": owner}


def counts(factory):
    with factory() as s:
        return tuple(s.scalar(select(func.count()).select_from(m)) for m in (Trip, TripCity, TripDay, TripActivity))


def create(client, cities, **extra):
    body = {"cities": cities, "generate": True, "pace": "balanced", **extra}
    return client.post("/api/trips", json=body, headers=h())


def places_of(day):
    return [a for a in day["activities"] if a["kind"] == "place"]


# --- Day allocation (unit) ------------------------------------------------------------


@pytest.mark.parametrize(
    "explicit, total, expected",
    [
        ([2, 3], None, [2, 3]),
        ([2, 3], 5, [2, 3]),
        ([None, None], 5, [3, 2]),  # earlier cities get the extra day
        ([None, None, None], 8, [3, 3, 2]),
        ([None, None, None], 3, [1, 1, 1]),
        ([4, None, None], 7, [4, 2, 1]),
        ([None], 6, [6]),
    ],
)
def test_allocate_days(explicit, total, expected):
    assert allocate_days(explicit, total) == expected


@pytest.mark.parametrize(
    "explicit, total, message",
    [
        ([2, 3], 6, "does not match"),
        ([None, None], None, "give days for every city"),
        ([None, None, None], 2, "less than one day"),
        ([5, None], 5, "less than one day"),
    ],
)
def test_allocate_days_errors(explicit, total, message):
    with pytest.raises(ValueError, match=message):
        allocate_days(explicit, total)


# --- Validation (API) ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"cities": [KYOTO, OSAKA], "num_days": 1},  # not enough days for 2 cities
        {"cities": [{**KYOTO, "days": 16}, {**OSAKA, "days": 15}]},  # 31 days
        {"cities": [KYOTO, OSAKA], "num_days": 31},
        {"cities": [{**KYOTO, "days": 2}, {**OSAKA, "days": 2}], "num_days": 5},  # mismatch
        {"cities": [KYOTO, OSAKA]},  # no days at all
        {"cities": [{**KYOTO, "days": 1}, {**KYOTO, "days": 1}]},  # same city twice in a row
        {"cities": [{**KYOTO, "days": 1}, {**KYOTO, "name": "kyoto", "latitude": 35.5, "days": 1}]},
        {"cities": [{**KYOTO, "days": 1}, {**OSAKA, "days": 1}], "planner": "ai", "generate": True},
        {"cities": [{**KYOTO, "name": f"C{i}", "latitude": 30 + i, "days": 1} for i in range(11)]},
        {"cities": [{**KYOTO, "days": 0}, {**OSAKA, "days": 1}]},
    ],
)
def test_multicity_validation(client, geo, factory, body):
    res = client.post("/api/trips", json={"generate": True, **body}, headers=h())
    assert res.status_code == 422, res.text
    assert geo["calls"] == [] and counts(factory) == (0, 0, 0, 0)


def test_revisiting_a_city_later_is_allowed(client):
    res = create(client, [{**KYOTO, "days": 1}, {**OSAKA, "days": 1}, {**KYOTO, "days": 1}])
    assert res.status_code == 201
    assert [c["name"] for c in res.json()["cities"]] == ["Kyoto", "Osaka", "Kyoto"]


# --- Generation ---------------------------------------------------------------------


def test_two_city_trip(client, geo, factory):
    res = create(client, [{**KYOTO, "days": 2}, {**OSAKA, "days": 1}], start_date="2026-11-03")
    assert res.status_code == 201, res.text
    trip = res.json()
    assert trip["num_days"] == 3 and trip["city_names"] == ["Kyoto", "Osaka"]
    assert trip["title"] == "Trip to Kyoto, Osaka"
    kyoto_id, osaka_id = (c["id"] for c in trip["cities"])
    assert [c["days"] for c in trip["cities"]] == [2, 1]
    assert [d["city_id"] for d in trip["days"]] == [kyoto_id, kyoto_id, osaka_id]
    assert [d["date"] for d in trip["days"]] == ["2026-11-03", "2026-11-04", "2026-11-05"]
    for d in trip["days"]:
        assert len(places_of(d)) == 3
        assert [a["slot"] for a in places_of(d)] == ["morning", "afternoon", "evening"]
    # Places come from the right city.
    assert all(a["name"].startswith("c35.01") for d in trip["days"][:2] for a in places_of(d))
    assert all(a["name"].startswith("c34.69") for a in places_of(trip["days"][2]))
    # Travel step ends the Kyoto section only.
    last_kyoto = trip["days"][1]["activities"][-1]
    assert last_kyoto["kind"] == "transfer" and last_kyoto["name"] == "Travel to Osaka"
    assert last_kyoto["slot"] is None and last_kyoto["latitude"] is None and last_kyoto["place_id"] is None
    assert last_kyoto["address"] == "Osaka, Japan"
    assert all(a["kind"] == "place" for a in trip["days"][0]["activities"] + trip["days"][2]["activities"])
    # One Geoapify search per city, around each city, in trip order.
    assert [c[:2] for c in geo["calls"]] == [(35.0116, 135.7681), (34.6937, 135.5023)]
    assert counts(factory) == (1, 2, 3, 10)  # 9 places + 1 travel step


def test_three_city_trip_with_total_days(client):
    trip = create(client, [KYOTO, OSAKA, NARA], num_days=7).json()
    assert [c["days"] for c in trip["cities"]] == [3, 2, 2]
    transfers = [(d["day_index"], a["name"]) for d in trip["days"] for a in d["activities"] if a["kind"] == "transfer"]
    assert transfers == [(2, "Travel to Osaka"), (4, "Travel to Nara")]
    assert [d["activities"][-1]["kind"] for d in trip["days"]][-1] == "place"


def test_city_order_is_kept(client):
    trip = create(client, [{**NARA, "days": 1}, {**KYOTO, "days": 1}, {**OSAKA, "days": 1}]).json()
    assert [c["name"] for c in trip["cities"]] == ["Nara", "Kyoto", "Osaka"]
    assert [c["position"] for c in trip["cities"]] == [0, 1, 2]
    city_by_id = {c["id"]: c["name"] for c in trip["cities"]}
    assert [city_by_id[d["city_id"]] for d in trip["days"]] == ["Nara", "Kyoto", "Osaka"]


def test_no_place_is_repeated_across_cities(client, geo):
    geo["shared_ids"] = True  # both cities' searches return the same place ids
    trip = create(client, [{**KYOTO, "days": 2}, {**OSAKA, "days": 2}]).json()
    ids = [a["place_id"] for d in trip["days"] for a in places_of(d)]
    assert len(ids) == len(set(ids)) == 12


def test_partial_results_in_one_city_warn_with_city_name(client, geo):
    geo["override"][OSAKA["latitude"]] = lambda r: httpx.Response(200, json={"features": features_around(34.69, 135.50, "few", 2)})
    trip = create(client, [{**KYOTO, "days": 1}, {**OSAKA, "days": 2}]).json()
    assert [len(places_of(d)) for d in trip["days"]] == [3, 1, 1]
    assert trip["warnings"] and trip["warnings"][0].startswith("Osaka: Only 2")


# --- Failures roll back completely ------------------------------------------------------


def test_insufficient_places_in_second_city(client, geo, factory):
    geo["override"][OSAKA["latitude"]] = lambda r: httpx.Response(200, json={"features": []})
    res = create(client, [{**KYOTO, "days": 1}, {**OSAKA, "days": 2}])
    assert res.status_code == 422
    assert "Not enough places found near Osaka to plan 2 days" in res.json()["detail"]
    assert counts(factory) == (0, 0, 0, 0)


@pytest.mark.parametrize("status, expected", [(500, 502), (429, 503)])
def test_geoapify_failure_in_second_city(client, geo, factory, status, expected):
    geo["override"][OSAKA["latitude"]] = lambda r: httpx.Response(status)
    res = create(client, [{**KYOTO, "days": 1}, {**OSAKA, "days": 1}])
    assert res.status_code == expected
    assert res.json()["detail"].startswith("Could not generate the itinerary for Osaka.")
    assert KEY not in res.text
    assert counts(factory) == (0, 0, 0, 0)


def test_timeout_in_third_city(client, geo, factory):
    def boom(request):
        raise httpx.ReadTimeout("slow", request=request)

    geo["override"][NARA["latitude"]] = boom
    res = create(client, [{**KYOTO, "days": 1}, {**OSAKA, "days": 1}, {**NARA, "days": 1}])
    assert res.status_code == 504 and "for Nara" in res.json()["detail"]
    assert counts(factory) == (0, 0, 0, 0)


def test_database_failure_rolls_back_whole_trip(client, factory, monkeypatch):
    original = SASession.flush

    def failing(self, *a, **k):
        if any(isinstance(o, TripActivity) and o.kind == "transfer" for o in self.new):
            raise OperationalError("INSERT", {}, Exception("outage"))
        return original(self, *a, **k)

    monkeypatch.setattr(SASession, "flush", failing)
    res = create(client, [{**KYOTO, "days": 1}, {**OSAKA, "days": 1}])
    monkeypatch.setattr(SASession, "flush", original)
    assert res.status_code == 503
    assert counts(factory) == (0, 0, 0, 0)


# --- Ownership -----------------------------------------------------------------------------


def test_other_browser_cannot_see_or_edit(client):
    trip = create(client, [{**KYOTO, "days": 1}, {**OSAKA, "days": 1}]).json()
    day = trip["days"][0]
    ids = [a["id"] for a in day["activities"]]
    assert client.get(f"/api/trips/{trip['id']}", headers=h(B)).status_code == 404
    assert client.put(f"/api/trips/{trip['id']}/days/{day['id']}/order",
                      json={"activity_ids": ids[::-1]}, headers=h(B)).status_code == 404
    assert client.delete(f"/api/trips/{trip['id']}/activities/{ids[-1]}", headers=h(B)).status_code == 404
    assert client.get(f"/api/trips/{trip['id']}", headers=h()).json() == trip


# --- Editing around travel steps ----------------------------------------------------------


@pytest.fixture
def two_city(client):
    return create(client, [{**KYOTO, "days": 1}, {**OSAKA, "days": 1}]).json()


def test_reorder_with_travel_step_labels_places_only(client, two_city):
    day = two_city["days"][0]
    ids = [a["id"] for a in day["activities"]]  # p, p, p, travel
    new_order = [ids[3], ids[2], ids[1], ids[0]]
    res = client.put(f"/api/trips/{two_city['id']}/days/{day['id']}/order", json={"activity_ids": new_order}, headers=h())
    acts = res.json()["days"][0]["activities"]
    assert [a["kind"] for a in acts] == ["transfer", "place", "place", "place"]
    assert [a["slot"] for a in acts] == [None, "morning", "afternoon", "evening"]


def test_travel_step_cannot_move_to_another_day(client, two_city):
    travel = two_city["days"][0]["activities"][-1]
    res = client.patch(f"/api/trips/{two_city['id']}/activities/{travel['id']}",
                       json={"day_id": two_city["days"][1]["id"]}, headers=h())
    assert res.status_code == 422 and "Travel steps" in res.json()["detail"]


def test_travel_step_can_be_removed_and_noted(client, two_city):
    travel = two_city["days"][0]["activities"][-1]
    url = f"/api/trips/{two_city['id']}/activities/{travel['id']}"
    noted = client.patch(url, json={"note": "Check train options"}, headers=h()).json()
    assert noted["days"][0]["activities"][-1]["note"] == "Check train options"
    after = client.delete(url, headers=h()).json()
    assert all(a["kind"] == "place" for a in after["days"][0]["activities"])


def test_added_and_moved_stops_go_before_travel_step(client, two_city):
    day0, day1 = two_city["days"]
    place = {"id": "saved-x", "name": "Saved X", "latitude": 35.02, "longitude": 135.77}
    added = client.post(f"/api/trips/{two_city['id']}/activities", json={"place": place, "day_id": day0["id"]},
                        headers=h()).json()
    acts = added["days"][0]["activities"]
    assert [a["kind"] for a in acts][-2:] == ["place", "transfer"] and acts[-2]["name"] == "Saved X"
    assert [a["slot"] for a in acts if a["kind"] == "place"] == ["morning", "morning", "afternoon", "evening"]
    mover = day1["activities"][0]
    moved = client.patch(f"/api/trips/{two_city['id']}/activities/{mover['id']}", json={"day_id": day0["id"]},
                         headers=h()).json()
    assert moved["days"][0]["activities"][-1]["kind"] == "transfer"
    assert moved["days"][0]["activities"][-2]["id"] == mover["id"]


def test_regenerate_keeps_travel_step_and_other_days(client, geo, two_city):
    day0, day1 = two_city["days"]
    res = client.post(f"/api/trips/{two_city['id']}/days/{day0['id']}/regenerate", headers=h())
    assert res.status_code == 200, res.text
    new0, new1 = res.json()["days"]
    assert new1 == day1
    assert new0["activities"][-1]["kind"] == "transfer" and new0["activities"][-1]["name"] == "Travel to Osaka"
    assert new0["activities"][-1]["id"] == day0["activities"][-1]["id"]
    assert len(places_of(new0)) == 3
    old_names = {a["name"] for a in places_of(day0)}
    assert not old_names & {a["name"] for a in places_of(new0)}  # fresh places preferred
    # Regeneration searched around the day's own city (Kyoto).
    assert geo["calls"][-1][:2] == (35.0116, 135.7681)


def test_regenerate_ai_on_multicity_trip_is_rejected(client, geo, two_city, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    before = len(geo["calls"])
    res = client.post(f"/api/trips/{two_city['id']}/days/{two_city['days'][0]['id']}/regenerate",
                      json={"planner": "ai"}, headers=h())
    assert res.status_code == 422 and "single-city" in res.json()["detail"]
    assert len(geo["calls"]) == before


def test_single_city_generation_unchanged(client):
    trip = create(client, [{**KYOTO, "days": 2}]).json()
    assert all(a["kind"] == "place" for d in trip["days"] for a in d["activities"])
    assert trip["city_names"] == ["Kyoto"]
