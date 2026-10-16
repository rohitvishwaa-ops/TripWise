"""Editing endpoints: reorder, move, note, delete, add, regenerate a day."""

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

from database import Base, TripActivity, TripDay, enable_sqlite_foreign_keys, get_db
from main import app
from places import get_http_client

A = str(uuid.uuid4())
B = str(uuid.uuid4())
KEY = "edit-test-key-not-real"
CITY = {"name": "Kyoto", "address": "Kyoto, Japan", "latitude": 35.0, "longitude": 135.75, "days": 2}

# Day 1 stops cluster around (35.00, 135.70); day 2 around (35.10, 135.80).
DAY_STOPS = [
    [("d1a", "Alpha", 35.000, 135.700), ("d1b", "Bravo", 35.002, 135.702), ("d1c", "Charlie", 35.004, 135.704)],
    [("d2a", "Delta", 35.100, 135.800), ("d2b", "Echo", 35.102, 135.802), ("d2c", "Foxtrot", 35.104, 135.804)],
]


@pytest.fixture
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def upstream(monkeypatch):
    monkeypatch.setenv("GEOAPIFY_API_KEY", KEY)
    calls = []
    state = {"features": [], "handler": None}

    def transport(request):
        calls.append(request)
        if state["handler"]:
            return state["handler"](request)
        return httpx.Response(200, json={"features": state["features"]})

    async def override():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as c:
            yield c

    app.dependency_overrides[get_http_client] = override
    yield state, calls
    app.dependency_overrides.pop(get_http_client, None)


@pytest.fixture
def client(factory, upstream):
    def override_get_db():
        with factory() as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def h(owner=A):
    return {"X-Trip-ID": owner}


def make_trip(client, factory, owner=A, interests=None):
    """A 2-day trip with three auto activities per day (no Geoapify needed)."""
    body = {"cities": [CITY], "pace": "balanced", "interests": interests or ["culture"]}
    trip = client.post("/api/trips", json=body, headers=h(owner)).json()
    with factory() as s:
        for day, stops in zip(trip["days"], DAY_STOPS):
            for pos, (pid, name, lat, lon) in enumerate(stops):
                s.add(TripActivity(day_id=day["id"], position=pos, kind="place", place_id=f"{pid}-{owner[:4]}",
                                   name=name, latitude=lat, longitude=lon, categories=["entertainment.museum"],
                                   slot=["morning", "afternoon", "evening"][pos], source="auto"))
        s.commit()
    return get(client, trip["id"], owner)


def get(client, trip_id, owner=A):
    res = client.get(f"/api/trips/{trip_id}", headers=h(owner))
    assert res.status_code == 200
    return res.json()


def names(day):
    return [a["name"] for a in day["activities"]]


def shape(day):
    return [(a["name"], a["position"], a["slot"]) for a in day["activities"]]


def feature(pid, name, lat, lon, cat="entertainment.museum"):
    return {"properties": {"place_id": pid, "name": name, "lat": lat, "lon": lon,
                           "formatted": f"{name}, Kyoto", "categories": [cat]},
            "geometry": {"coordinates": [lon, lat]}}


# --- Reorder -----------------------------------------------------------------


def test_reorder_day(client, factory):
    trip = make_trip(client, factory)
    day = trip["days"][0]
    ids = [a["id"] for a in day["activities"]][::-1]
    res = client.put(f"/api/trips/{trip['id']}/days/{day['id']}/order", json={"activity_ids": ids}, headers=h())
    assert res.status_code == 200
    new_day = res.json()["days"][0]
    assert shape(new_day) == [("Charlie", 0, "morning"), ("Bravo", 1, "afternoon"), ("Alpha", 2, "evening")]
    assert res.json()["updated_at"] >= trip["updated_at"]
    # Persisted, other day untouched.
    again = get(client, trip["id"])
    assert shape(again["days"][0]) == shape(new_day)
    assert again["days"][1] == trip["days"][1]


def test_reorder_empty_day(client):
    trip = client.post("/api/trips", json={"cities": [CITY]}, headers=h()).json()
    day = trip["days"][0]
    res = client.put(f"/api/trips/{trip['id']}/days/{day['id']}/order", json={"activity_ids": []}, headers=h())
    assert res.status_code == 200


@pytest.mark.parametrize(
    "make_ids",
    [
        lambda d0, d1: [d0[0], d0[0], d0[1]],  # duplicate
        lambda d0, d1: d0[:2],  # missing one
        lambda d0, d1: d0 + [d1[0]],  # extra from another day
        lambda d0, d1: [d0[0], d0[1], d1[0]],  # swapped in another day's activity
        lambda d0, d1: [],  # empty for a non-empty day
        lambda d0, d1: d0 + [999999],  # unknown id
        lambda d0, d1: ["one", "two", "three"],  # not integers
        lambda d0, d1: None,  # missing list
    ],
)
def test_reorder_rejects_malformed(client, factory, make_ids):
    trip = make_trip(client, factory)
    d0 = [a["id"] for a in trip["days"][0]["activities"]]
    d1 = [a["id"] for a in trip["days"][1]["activities"]]
    ids = make_ids(d0, d1)
    body = {} if ids is None else {"activity_ids": ids}
    res = client.put(f"/api/trips/{trip['id']}/days/{trip['days'][0]['id']}/order", json=body, headers=h())
    assert res.status_code == 422
    assert get(client, trip["id"]) == trip


def test_reorder_extra_field_rejected(client, factory):
    trip = make_trip(client, factory)
    ids = [a["id"] for a in trip["days"][0]["activities"]]
    res = client.put(f"/api/trips/{trip['id']}/days/{trip['days'][0]['id']}/order",
                     json={"activity_ids": ids, "force": True}, headers=h())
    assert res.status_code == 422


def test_reorder_unknown_or_foreign_day(client, factory):
    trip = make_trip(client, factory)
    other = make_trip(client, factory)  # same owner, different trip
    ids = [a["id"] for a in trip["days"][0]["activities"]]
    for day_id in (999999, other["days"][0]["id"]):
        res = client.put(f"/api/trips/{trip['id']}/days/{day_id}/order", json={"activity_ids": ids}, headers=h())
        assert res.status_code == 404
        assert res.json()["detail"] == "Day not found in this trip."
    assert client.put(f"/api/trips/{trip['id']}/days/0/order", json={"activity_ids": ids}, headers=h()).status_code == 422


# --- Move ---------------------------------------------------------------------


def test_move_to_other_day_appends_and_relabels(client, factory):
    trip = make_trip(client, factory)
    bravo = trip["days"][0]["activities"][1]
    res = client.patch(f"/api/trips/{trip['id']}/activities/{bravo['id']}",
                       json={"day_id": trip["days"][1]["id"]}, headers=h())
    assert res.status_code == 200
    d0, d1 = res.json()["days"]
    assert shape(d0) == [("Alpha", 0, "morning"), ("Charlie", 1, "afternoon")]
    assert names(d1) == ["Delta", "Echo", "Foxtrot", "Bravo"]
    assert [a["slot"] for a in d1["activities"]] == ["morning", "morning", "afternoon", "evening"]
    assert d1["activities"][-1]["id"] == bravo["id"]  # same row, moved
    assert get(client, trip["id"])["days"] == res.json()["days"]


def test_move_to_position_in_other_day(client, factory):
    trip = make_trip(client, factory)
    alpha = trip["days"][0]["activities"][0]
    res = client.patch(f"/api/trips/{trip['id']}/activities/{alpha['id']}",
                       json={"day_id": trip["days"][1]["id"], "position": 0}, headers=h())
    assert names(res.json()["days"][1]) == ["Alpha", "Delta", "Echo", "Foxtrot"]


def test_move_within_day_by_position(client, factory):
    trip = make_trip(client, factory)
    charlie = trip["days"][0]["activities"][2]
    res = client.patch(f"/api/trips/{trip['id']}/activities/{charlie['id']}", json={"position": 0}, headers=h())
    assert shape(res.json()["days"][0]) == [("Charlie", 0, "morning"), ("Alpha", 1, "afternoon"), ("Bravo", 2, "evening")]


def test_move_last_activity_leaves_day_empty(client, factory):
    trip = make_trip(client, factory)
    day0 = trip["days"][0]
    for a in day0["activities"]:
        client.patch(f"/api/trips/{trip['id']}/activities/{a['id']}", json={"day_id": trip["days"][1]["id"]}, headers=h())
    after = get(client, trip["id"])
    assert after["days"][0]["activities"] == []
    assert len(after["days"][1]["activities"]) == 6
    assert [a["position"] for a in after["days"][1]["activities"]] == list(range(6))


@pytest.mark.parametrize(
    "body_fn",
    [
        lambda t, o: {"day_id": o["days"][0]["id"]},  # day of another trip
        lambda t, o: {"day_id": 999999},
        lambda t, o: {"day_id": None},
        lambda t, o: {"day_id": 0},
        lambda t, o: {"position": 4},  # day 1 has 3 -> max index after removal is 2
        lambda t, o: {"position": -1},
        lambda t, o: {},
        lambda t, o: {"trip_id": t["id"]},
        lambda t, o: {"note": "x" * 501},
    ],
)
def test_update_activity_rejects_invalid(client, factory, body_fn):
    trip = make_trip(client, factory)
    other = make_trip(client, factory)
    act = trip["days"][0]["activities"][0]
    res = client.patch(f"/api/trips/{trip['id']}/activities/{act['id']}", json=body_fn(trip, other), headers=h())
    assert res.status_code == 422, res.text
    assert get(client, trip["id"]) == trip


def test_activity_of_another_trip_is_not_found(client, factory):
    trip = make_trip(client, factory)
    other = make_trip(client, factory)
    foreign = other["days"][0]["activities"][0]
    url = f"/api/trips/{trip['id']}/activities/{foreign['id']}"
    assert client.patch(url, json={"note": "x"}, headers=h()).status_code == 404
    assert client.delete(url, headers=h()).status_code == 404
    assert get(client, other["id"]) == other


# --- Notes ----------------------------------------------------------------------


def test_note_set_trim_and_clear(client, factory):
    trip = make_trip(client, factory)
    act = trip["days"][0]["activities"][1]
    url = f"/api/trips/{trip['id']}/activities/{act['id']}"
    res = client.patch(url, json={"note": "  Book tickets online  "}, headers=h())
    assert res.json()["days"][0]["activities"][1]["note"] == "Book tickets online"
    assert shape(res.json()["days"][0]) == shape(trip["days"][0])  # order unchanged
    assert get(client, trip["id"])["days"][0]["activities"][1]["note"] == "Book tickets online"
    res = client.patch(url, json={"note": "   "}, headers=h())
    assert res.json()["days"][0]["activities"][1]["note"] is None
    res = client.patch(url, json={"note": None}, headers=h())
    assert res.status_code == 200


def test_note_max_length(client, factory):
    trip = make_trip(client, factory)
    act = trip["days"][0]["activities"][0]
    url = f"/api/trips/{trip['id']}/activities/{act['id']}"
    assert client.patch(url, json={"note": "n" * 500}, headers=h()).status_code == 200


# --- Delete ---------------------------------------------------------------------


def test_delete_activity(client, factory):
    trip = make_trip(client, factory)
    alpha = trip["days"][0]["activities"][0]
    url = f"/api/trips/{trip['id']}/activities/{alpha['id']}"
    res = client.delete(url, headers=h())
    assert res.status_code == 200
    assert shape(res.json()["days"][0]) == [("Bravo", 0, "morning"), ("Charlie", 1, "afternoon")]
    assert client.delete(url, headers=h()).status_code == 404
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(TripActivity)) == 5


# --- Authorization ---------------------------------------------------------------


def test_other_browser_cannot_edit(client, factory, upstream):
    _, calls = upstream
    trip = make_trip(client, factory)
    d0 = trip["days"][0]
    act = d0["activities"][0]
    tid = trip["id"]
    ids = [a["id"] for a in d0["activities"]]
    place = {"id": "new", "name": "New", "latitude": 35.0, "longitude": 135.7}
    for res in (
        client.put(f"/api/trips/{tid}/days/{d0['id']}/order", json={"activity_ids": ids[::-1]}, headers=h(B)),
        client.patch(f"/api/trips/{tid}/activities/{act['id']}", json={"note": "mine now"}, headers=h(B)),
        client.delete(f"/api/trips/{tid}/activities/{act['id']}", headers=h(B)),
        client.post(f"/api/trips/{tid}/activities", json={"place": place}, headers=h(B)),
        client.post(f"/api/trips/{tid}/days/{d0['id']}/regenerate", headers=h(B)),
    ):
        assert res.status_code == 404
        assert res.json()["detail"] == "Trip not found."
    assert calls == []  # regenerate never reached Geoapify
    assert get(client, tid) == trip


@pytest.mark.parametrize("headers", [{}, {"X-Trip-ID": "nope"}])
def test_requires_browser_id(client, factory, headers):
    trip = make_trip(client, factory)
    act = trip["days"][0]["activities"][0]
    assert client.patch(f"/api/trips/{trip['id']}/activities/{act['id']}", json={"note": "x"}, headers=headers).status_code == 400


# --- Add saved place --------------------------------------------------------------


def test_add_to_given_day(client, factory):
    trip = make_trip(client, factory)
    place = {"id": "saved-1", "name": "Kinkaku-ji", "address": "Kinkaku-ji, Kyoto",
             "latitude": 35.0394, "longitude": 135.7292, "categories": ["tourism.sights"]}
    res = client.post(f"/api/trips/{trip['id']}/activities",
                      json={"place": place, "day_id": trip["days"][1]["id"], "note": " Go early "}, headers=h())
    assert res.status_code == 201
    added = res.json()["days"][1]["activities"][-1]
    assert (added["name"], added["source"], added["position"], added["note"]) == ("Kinkaku-ji", "user", 3, "Go early")
    assert [a["slot"] for a in res.json()["days"][1]["activities"]] == ["morning", "morning", "afternoon", "evening"]
    assert get(client, trip["id"])["days"][1]["activities"][-1]["place_id"] == "saved-1"


def test_add_picks_the_closest_day(client, factory):
    trip = make_trip(client, factory)
    near_day2 = {"id": "near-2", "name": "Near day two", "latitude": 35.101, "longitude": 135.801}
    res = client.post(f"/api/trips/{trip['id']}/activities", json={"place": near_day2}, headers=h())
    assert names(res.json()["days"][1])[-1] == "Near day two"
    near_day1 = {"id": "near-1", "name": "Near day one", "latitude": 35.001, "longitude": 135.701}
    res = client.post(f"/api/trips/{trip['id']}/activities", json={"place": near_day1}, headers=h())
    assert names(res.json()["days"][0])[-1] == "Near day one"


def test_add_to_trip_with_empty_days_uses_first_day(client):
    trip = client.post("/api/trips", json={"cities": [CITY]}, headers=h()).json()
    res = client.post(f"/api/trips/{trip['id']}/activities",
                      json={"place": {"id": "x", "name": "X", "latitude": 35, "longitude": 135}}, headers=h())
    assert names(res.json()["days"][0]) == ["X"]
    assert res.json()["days"][0]["activities"][0]["slot"] == "morning"


@pytest.mark.parametrize(
    "place",
    [
        {"id": "d1a-" + A[:4], "name": "Other name", "latitude": 1, "longitude": 1},  # same place id
        {"id": "different", "name": "alpha", "latitude": 35.0001, "longitude": 135.7001},  # same name + spot
    ],
)
def test_add_rejects_place_already_in_trip(client, factory, place):
    trip = make_trip(client, factory)
    res = client.post(f"/api/trips/{trip['id']}/activities", json={"place": place}, headers=h())
    assert res.status_code == 409
    assert get(client, trip["id"]) == trip


@pytest.mark.parametrize(
    "body_fn",
    [
        lambda o: {"place": {"id": "p", "name": "P", "latitude": 1, "longitude": 1}, "day_id": o["days"][0]["id"]},
        lambda o: {"place": {"id": "p", "name": "P", "latitude": 1, "longitude": 1}, "day_id": 999999},
        lambda o: {"place": {"id": "p", "name": "P", "latitude": 91, "longitude": 1}},
        lambda o: {"place": {"id": "bad id", "name": "P", "latitude": 1, "longitude": 1}},
        lambda o: {"place": {"name": "P", "latitude": 1, "longitude": 1}},
        lambda o: {},
        lambda o: {"place": {"id": "p", "name": "P", "latitude": 1, "longitude": 1}, "source": "auto"},
    ],
)
def test_add_rejects_invalid(client, factory, body_fn):
    trip = make_trip(client, factory)
    other = make_trip(client, factory)
    res = client.post(f"/api/trips/{trip['id']}/activities", json=body_fn(other), headers=h())
    assert res.status_code == 422, res.text
    assert get(client, trip["id"]) == trip


# --- Regenerate ----------------------------------------------------------------------


def candidates_with_conflicts(owner=A):
    """Geoapify answer that includes places already on day 1 and day 2."""
    s = owner[:4]
    return [
        feature(f"d2a-{s}", "Delta", 35.100, 135.800),  # on the other day: must never be used
        feature(f"d2b-{s}", "Echo", 35.102, 135.802),
        feature(f"d1a-{s}", "Alpha", 35.000, 135.700),  # currently on this day: avoided
        feature("new-1", "Museum One", 35.010, 135.710),
        feature("new-2", "Museum Two", 35.013, 135.712),
        feature("new-3", "Museum Three", 35.016, 135.715),
        feature("new-4", "Museum Four", 35.019, 135.718),
    ]


def test_regenerate_replaces_only_that_day(client, factory, upstream):
    state, calls = upstream
    state["features"] = candidates_with_conflicts()
    trip = make_trip(client, factory)
    # A note on the other day must survive.
    other_act = trip["days"][1]["activities"][0]
    client.patch(f"/api/trips/{trip['id']}/activities/{other_act['id']}", json={"note": "keep me"}, headers=h())
    before = get(client, trip["id"])

    res = client.post(f"/api/trips/{trip['id']}/days/{trip['days'][0]['id']}/regenerate", headers=h())
    assert res.status_code == 200, res.text
    body = res.json()
    new_day = body["days"][0]
    assert names(new_day) and set(names(new_day)) <= {"Museum One", "Museum Two", "Museum Three", "Museum Four"}
    assert len(new_day["activities"]) == 3
    assert [a["slot"] for a in new_day["activities"]] == ["morning", "afternoon", "evening"]
    assert all(a["source"] == "auto" for a in new_day["activities"])
    assert new_day["theme"] == "Culture" and new_day["generated_by"] == "auto"
    assert body["days"][1] == before["days"][1]  # untouched, note kept
    ids = [a["place_id"] for d in body["days"] for a in d["activities"]]
    assert len(ids) == len(set(ids))  # no duplicates anywhere in the trip
    assert get(client, trip["id"])["days"] == body["days"]
    q = parse_qs(urlparse(str(calls[0].url)).query)
    assert q["filter"] == ["circle:135.75,35.0,10000"]  # around the day's city


def test_regenerate_falls_back_to_current_places(client, factory, upstream):
    state, _ = upstream
    s = A[:4]
    # Only the day's own places (and other-day places) exist.
    state["features"] = [feature(f"d1{x}-{s}", n, 35.0 + i * 0.002, 135.70 + i * 0.002)
                         for i, (x, n) in enumerate([("a", "Alpha"), ("b", "Bravo"), ("c", "Charlie")])]
    state["features"] += [feature(f"d2a-{s}", "Delta", 35.1, 135.8)]
    trip = make_trip(client, factory)
    res = client.post(f"/api/trips/{trip['id']}/days/{trip['days'][0]['id']}/regenerate", headers=h())
    assert res.status_code == 200
    assert sorted(names(res.json()["days"][0])) == ["Alpha", "Bravo", "Charlie"]
    assert "Delta" not in names(res.json()["days"][0])


def test_regenerate_with_fewer_places_warns(client, factory, upstream):
    state, _ = upstream
    state["features"] = [feature("only-1", "Lonely Museum", 35.01, 135.71)]
    trip = make_trip(client, factory)
    # Move day 1's places away so they are not reusable by day 1 (they are on day 2 now).
    for a in trip["days"][0]["activities"]:
        client.patch(f"/api/trips/{trip['id']}/activities/{a['id']}", json={"day_id": trip["days"][1]["id"]}, headers=h())
    res = client.post(f"/api/trips/{trip['id']}/days/{trip['days'][0]['id']}/regenerate", headers=h())
    assert res.status_code == 200
    assert names(res.json()["days"][0]) == ["Lonely Museum"]
    assert "Only 1" in res.json()["warnings"][0]


def test_regenerate_with_nothing_usable_changes_nothing(client, factory, upstream):
    state, _ = upstream
    s = A[:4]
    state["features"] = [feature(f"d2a-{s}", "Delta", 35.1, 135.8)]  # only other-day places
    trip = make_trip(client, factory)
    for a in trip["days"][0]["activities"]:
        client.delete(f"/api/trips/{trip['id']}/activities/{a['id']}", headers=h())
    before = get(client, trip["id"])
    res = client.post(f"/api/trips/{trip['id']}/days/{trip['days'][0]['id']}/regenerate", headers=h())
    assert res.status_code == 422
    assert "No other places were found near Kyoto" in res.json()["detail"]
    assert get(client, trip["id"]) == before


@pytest.mark.parametrize("status, expected", [(500, 502), (429, 503)])
def test_regenerate_upstream_error_changes_nothing(client, factory, upstream, status, expected):
    state, _ = upstream
    state["handler"] = lambda r: httpx.Response(status, json={"message": KEY})
    trip = make_trip(client, factory)
    res = client.post(f"/api/trips/{trip['id']}/days/{trip['days'][0]['id']}/regenerate", headers=h())
    assert res.status_code == expected
    assert res.json()["detail"].startswith("Could not regenerate the day.")
    assert KEY not in res.text
    assert get(client, trip["id"]) == trip


def test_regenerate_timeout_changes_nothing(client, factory, upstream):
    state, _ = upstream

    def boom(request):
        raise httpx.ReadTimeout("slow", request=request)

    state["handler"] = boom
    trip = make_trip(client, factory)
    assert client.post(f"/api/trips/{trip['id']}/days/{trip['days'][0]['id']}/regenerate", headers=h()).status_code == 504
    assert get(client, trip["id"]) == trip


def test_regenerate_missing_key(client, factory, upstream, monkeypatch):
    _, calls = upstream
    trip = make_trip(client, factory)
    monkeypatch.delenv("GEOAPIFY_API_KEY")
    res = client.post(f"/api/trips/{trip['id']}/days/{trip['days'][0]['id']}/regenerate", headers=h())
    assert res.status_code == 503 and calls == []
    assert get(client, trip["id"]) == trip


def test_regenerate_unknown_day(client, factory, upstream):
    _, calls = upstream
    trip = make_trip(client, factory)
    other = make_trip(client, factory)
    for day_id in (999999, other["days"][0]["id"]):
        assert client.post(f"/api/trips/{trip['id']}/days/{day_id}/regenerate", headers=h()).status_code == 404
    assert calls == []


# --- Transactions -------------------------------------------------------------------


def failing_flush_on(monkeypatch, predicate):
    original = SASession.flush

    def flush(self, *args, **kwargs):
        if predicate(self):
            raise OperationalError("UPDATE", {}, Exception("password=secretpw"))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(SASession, "flush", flush)
    return lambda: monkeypatch.setattr(SASession, "flush", original)


def test_reorder_rolls_back_on_database_error(client, factory, monkeypatch):
    trip = make_trip(client, factory)
    day = trip["days"][0]
    restore = failing_flush_on(monkeypatch, lambda s: bool(s.dirty))
    res = client.put(f"/api/trips/{trip['id']}/days/{day['id']}/order",
                     json={"activity_ids": [a["id"] for a in day["activities"]][::-1]}, headers=h())
    restore()
    assert res.status_code == 503 and "secretpw" not in res.text
    assert get(client, trip["id"]) == trip


def test_move_rolls_back_on_database_error(client, factory, monkeypatch):
    trip = make_trip(client, factory)
    act = trip["days"][0]["activities"][0]
    restore = failing_flush_on(monkeypatch, lambda s: bool(s.dirty))
    res = client.patch(f"/api/trips/{trip['id']}/activities/{act['id']}", json={"day_id": trip["days"][1]["id"]}, headers=h())
    restore()
    assert res.status_code == 503
    assert get(client, trip["id"]) == trip


def test_regenerate_rolls_back_on_database_error(client, factory, upstream, monkeypatch):
    state, _ = upstream
    state["features"] = candidates_with_conflicts()
    trip = make_trip(client, factory)
    restore = failing_flush_on(monkeypatch, lambda s: any(isinstance(o, TripActivity) for o in s.new))
    res = client.post(f"/api/trips/{trip['id']}/days/{trip['days'][0]['id']}/regenerate", headers=h())
    restore()
    assert res.status_code == 503
    after = get(client, trip["id"])
    assert after == trip  # old activities NOT deleted: the whole replacement rolled back
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(TripActivity)) == 6
        assert s.scalar(select(func.count()).select_from(TripDay)) == 2
