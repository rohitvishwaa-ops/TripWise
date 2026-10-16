import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import (
    Base,
    ItineraryItem,
    Trip,
    TripActivity,
    TripCity,
    TripDay,
    enable_sqlite_foreign_keys,
    get_db,
)
from main import app

OWNER_A = str(uuid.uuid4())
OWNER_B = str(uuid.uuid4())

KYOTO = {"name": "Kyoto", "address": "Kyoto, Japan", "latitude": 35.0116, "longitude": 135.7681, "days": 3}
OSAKA = {"name": "Osaka", "address": "Osaka, Japan", "latitude": 34.6937, "longitude": 135.5023, "days": 2}


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def client(factory):
    def override_get_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def h(owner=OWNER_A):
    return {"X-Trip-ID": owner}


def create(client, owner=OWNER_A, **overrides):
    body = {"cities": [KYOTO], **overrides}
    res = client.post("/api/trips", json=body, headers=h(owner))
    assert res.status_code == 201, res.text
    return res.json()


def counts(factory):
    with factory() as s:
        return {
            model.__tablename__: s.scalar(select(func.count()).select_from(model))
            for model in (Trip, TripCity, TripDay, TripActivity)
        }


def add_activities(factory, trip_id, per_day=2):
    with factory() as s:
        days = s.scalars(select(TripDay).where(TripDay.trip_id == trip_id)).all()
        for day in days:
            for i in range(per_day):
                s.add(TripActivity(day_id=day.id, position=i, name=f"Stop {i}", source="user", categories=[]))
        s.commit()


# --- Create ----------------------------------------------------------------


def test_foreign_keys_are_enforced_in_sqlite(engine):
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_create_minimal_trip(client):
    trip = create(client)
    assert uuid.UUID(trip["id"])
    assert trip["title"] == "Trip to Kyoto"
    assert trip["num_days"] == 3
    assert trip["pace"] == "balanced"
    assert trip["interests"] == []
    assert trip["planner"] == "auto"
    assert trip["start_date"] is None and trip["end_date"] is None
    assert trip["city_names"] == ["Kyoto"]
    city = trip["cities"][0]
    assert {k: city[k] for k in KYOTO} == KYOTO
    assert city["position"] == 0
    assert [d["day_index"] for d in trip["days"]] == [0, 1, 2]
    assert all(d["city_id"] == city["id"] and d["activities"] == [] and d["date"] is None for d in trip["days"])


def test_create_full_trip_with_dates_and_two_cities(client):
    trip = create(
        client,
        title="  Kansai   spring ",
        start_date="2026-11-03",
        pace="relaxed",
        interests=["culture", "food", "culture"],
        cities=[KYOTO, OSAKA],
    )
    assert trip["title"] == "Kansai spring"
    assert trip["num_days"] == 5
    assert trip["interests"] == ["culture", "food"]  # deduplicated
    assert trip["end_date"] == "2026-11-07"
    assert [d["date"] for d in trip["days"]] == [
        "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-07",
    ]
    kyoto_id, osaka_id = (c["id"] for c in trip["cities"])
    assert [d["city_id"] for d in trip["days"]] == [kyoto_id] * 3 + [osaka_id] * 2


def test_default_title_for_many_cities(client):
    cities = [{**KYOTO, "name": n, "days": 1, "latitude": 35 + i} for i, n in enumerate("ABCD")]
    assert create(client, cities=cities)["title"] == "Trip to A, B, C and more"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"cities": []},
        {"cities": [{**KYOTO, "days": 0}]},
        {"cities": [{**KYOTO, "days": 31}]},
        {"cities": [{**KYOTO, "days": 16}, {**OSAKA, "days": 15}]},  # 31 total
        {"cities": [{**KYOTO, "days": 1}] * 11},
        {"cities": [{**KYOTO, "latitude": 91}]},
        {"cities": [{**KYOTO, "longitude": -181}]},
        {"cities": [{**KYOTO, "name": ""}]},
        {"cities": [{**KYOTO, "name": "x" * 201}]},
        {"cities": [{k: v for k, v in KYOTO.items() if k != "latitude"}]},
        {"cities": [{**KYOTO, "unknown": 1}]},
        {"cities": [KYOTO], "pace": "fast"},
        {"cities": [KYOTO], "interests": ["skydiving"]},
        {"cities": [KYOTO], "interests": "culture"},
        {"cities": [KYOTO], "start_date": "2026-13-01"},
        {"cities": [KYOTO], "start_date": "next week"},
        {"cities": [KYOTO], "title": "   "},
        {"cities": [KYOTO], "title": "t" * 121},
        {"cities": [KYOTO], "owner_id": OWNER_B},  # cannot set owner via body
        {"cities": [KYOTO], "planner": "ai"},  # not settable yet
    ],
)
def test_create_validation(client, factory, body):
    res = client.post("/api/trips", json=body, headers=h())
    assert res.status_code == 422, res.text
    assert counts(factory)["trips"] == 0


def test_create_accepts_exactly_30_days(client):
    trip = create(client, cities=[{**KYOTO, "days": 15}, {**OSAKA, "days": 15}])
    assert trip["num_days"] == 30 and len(trip["days"]) == 30


# --- X-Trip-ID --------------------------------------------------------------


@pytest.mark.parametrize("headers", [{}, {"X-Trip-ID": "nope"}, {"X-Trip-ID": "{" + OWNER_A + "}"}])
@pytest.mark.parametrize(
    "method, path",
    [("get", "/api/trips"), ("post", "/api/trips"), ("get", f"/api/trips/{uuid.uuid4()}"),
     ("patch", f"/api/trips/{uuid.uuid4()}"), ("delete", f"/api/trips/{uuid.uuid4()}")],
)
def test_requires_valid_browser_id(client, headers, method, path):
    kwargs = {"json": {"cities": [KYOTO], "title": "x"}} if method in ("post", "patch") else {}
    res = getattr(client, method)(path, headers=headers, **kwargs)
    assert res.status_code == 400
    assert "X-Trip-ID" in res.json()["detail"]


# --- List / get -------------------------------------------------------------


def test_list_only_own_trips_newest_first(client):
    first = create(client, title="First")
    second = create(client, title="Second")
    create(client, owner=OWNER_B, title="Someone else's")
    body = client.get("/api/trips", headers=h()).json()
    assert body["count"] == 2
    assert [t["id"] for t in body["trips"]] == [second["id"], first["id"]]
    assert "days" not in body["trips"][0] and body["trips"][0]["city_names"] == ["Kyoto"]


def test_list_empty(client):
    assert client.get("/api/trips", headers=h()).json() == {"count": 0, "trips": []}


def test_get_trip(client):
    trip = create(client)
    res = client.get(f"/api/trips/{trip['id']}", headers=h())
    assert res.status_code == 200
    assert res.json() == trip


def test_get_missing_trip(client):
    res = client.get(f"/api/trips/{uuid.uuid4()}", headers=h())
    assert res.status_code == 404
    assert res.json()["detail"] == "Trip not found."


def test_get_invalid_trip_id(client):
    assert client.get("/api/trips/not-a-uuid", headers=h()).status_code == 422


def test_trip_id_is_case_insensitive(client):
    trip = create(client)
    assert client.get(f"/api/trips/{trip['id'].upper()}", headers=h()).status_code == 200


# --- Cross-browser isolation ------------------------------------------------


def test_other_browser_cannot_read_update_or_delete(client, factory):
    trip = create(client, title="Private")
    url = f"/api/trips/{trip['id']}"
    for res in (
        client.get(url, headers=h(OWNER_B)),
        client.patch(url, json={"title": "Hijacked"}, headers=h(OWNER_B)),
        client.delete(url, headers=h(OWNER_B)),
    ):
        assert res.status_code == 404  # same as missing: existence not revealed
    still = client.get(url, headers=h()).json()
    assert still["title"] == "Private"
    assert counts(factory)["trips"] == 1


# --- Update -----------------------------------------------------------------


def test_update_fields(client):
    trip = create(client)
    res = client.patch(
        f"/api/trips/{trip['id']}",
        json={"title": "Kyoto in autumn", "pace": "packed", "interests": ["nature", "nature", "food"]},
        headers=h(),
    )
    assert res.status_code == 200
    body = res.json()
    assert (body["title"], body["pace"], body["interests"]) == ("Kyoto in autumn", "packed", ["nature", "food"])
    assert body["updated_at"] >= trip["updated_at"]
    assert body["created_at"] == trip["created_at"]
    assert body["cities"] == trip["cities"]


def test_update_start_date_sets_and_clears_day_dates(client):
    trip = create(client)
    url = f"/api/trips/{trip['id']}"
    body = client.patch(url, json={"start_date": "2026-12-30"}, headers=h()).json()
    assert [d["date"] for d in body["days"]] == ["2026-12-30", "2026-12-31", "2027-01-01"]
    assert body["end_date"] == "2027-01-01"
    body = client.patch(url, json={"start_date": None}, headers=h()).json()
    assert body["start_date"] is None and body["end_date"] is None
    assert all(d["date"] is None for d in body["days"])


def test_update_moves_trip_to_top_of_list(client):
    first = create(client, title="First")
    create(client, title="Second")
    client.patch(f"/api/trips/{first['id']}", json={"title": "First, edited"}, headers=h())
    assert client.get("/api/trips", headers=h()).json()["trips"][0]["id"] == first["id"]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"title": None},
        {"title": "  "},
        {"title": "t" * 121},
        {"pace": None},
        {"pace": "fast"},
        {"interests": None},
        {"interests": ["skydiving"]},
        {"start_date": "31/12/2026"},
        {"cities": [KYOTO]},  # structure is changed by later planner endpoints
        {"num_days": 5},
        {"owner_id": OWNER_B},
    ],
)
def test_update_validation(client, body):
    trip = create(client)
    res = client.patch(f"/api/trips/{trip['id']}", json=body, headers=h())
    assert res.status_code == 422, res.text
    assert client.get(f"/api/trips/{trip['id']}", headers=h()).json() == trip


def test_update_missing_trip(client):
    res = client.patch(f"/api/trips/{uuid.uuid4()}", json={"title": "x"}, headers=h())
    assert res.status_code == 404


# --- Delete and cascades ----------------------------------------------------


def test_delete_trip_cascades_to_cities_days_and_activities(client, factory):
    keep = create(client, title="Keep", cities=[OSAKA])
    trip = create(client, cities=[KYOTO, OSAKA])
    add_activities(factory, trip["id"])
    add_activities(factory, keep["id"])
    assert counts(factory) == {"trips": 2, "trip_cities": 3, "trip_days": 7, "trip_activities": 14}

    res = client.delete(f"/api/trips/{trip['id']}", headers=h())
    assert res.status_code == 204 and res.content == b""
    assert client.get(f"/api/trips/{trip['id']}", headers=h()).status_code == 404
    assert client.delete(f"/api/trips/{trip['id']}", headers=h()).status_code == 404
    # Only the other trip's rows remain.
    assert counts(factory) == {"trips": 1, "trip_cities": 1, "trip_days": 2, "trip_activities": 4}


def test_database_level_cascade_without_orm(client, factory):
    trip = create(client, cities=[KYOTO, OSAKA])
    add_activities(factory, trip["id"])
    with factory() as s:
        s.execute(text("DELETE FROM trips WHERE id = :id"), {"id": trip["id"]})
        s.commit()
    assert counts(factory) == {"trips": 0, "trip_cities": 0, "trip_days": 0, "trip_activities": 0}


def test_deleting_a_city_cascades_to_its_days(client, factory):
    trip = create(client, cities=[KYOTO, OSAKA])
    add_activities(factory, trip["id"], per_day=1)
    with factory() as s:
        s.execute(text("DELETE FROM trip_cities WHERE id = :id"), {"id": trip["cities"][1]["id"]})
        s.commit()
    assert counts(factory) == {"trips": 1, "trip_cities": 1, "trip_days": 3, "trip_activities": 3}


@pytest.mark.parametrize(
    "row",
    [
        lambda: TripCity(trip_id=str(uuid.uuid4()), position=0, name="X", latitude=0, longitude=0, days=1),
        lambda: TripDay(trip_id=str(uuid.uuid4()), city_id=999, day_index=0),
        lambda: TripActivity(day_id=999, position=0, name="X", source="user", categories=[]),
    ],
)
def test_orphan_rows_rejected_by_foreign_keys(factory, row):
    with factory() as s:
        s.add(row())
        with pytest.raises(IntegrityError):
            s.commit()


@pytest.mark.parametrize(
    "bad",
    [
        {"pace": "fast"},
        {"planner": "magic"},
        {"num_days": 0},
        {"num_days": 31},
    ],
)
def test_check_constraints_enforced_in_database(factory, bad):
    fields = {"owner_id": OWNER_A, "title": "T", "num_days": 1, "pace": "balanced", "planner": "auto", "interests": [], **bad}
    with factory() as s:
        s.add(Trip(**fields))
        with pytest.raises(IntegrityError):
            s.commit()


def test_duplicate_day_index_rejected(client, factory):
    trip = create(client)
    with factory() as s:
        s.add(TripDay(trip_id=trip["id"], city_id=trip["cities"][0]["id"], day_index=0))
        with pytest.raises(IntegrityError):
            s.commit()


# --- Coexistence and failures -----------------------------------------------


def test_trips_do_not_touch_saved_places(client, factory):
    client.post(
        "/api/itinerary",
        json={"id": "p1", "name": "Kinkaku-ji", "latitude": 35.03, "longitude": 135.72},
        headers=h(),
    )
    trip = create(client)
    client.delete(f"/api/trips/{trip['id']}", headers=h())
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(ItineraryItem)) == 1
    assert client.get("/api/itinerary", headers=h()).json()["count"] == 1


def test_not_configured_returns_503():
    res = TestClient(app).get("/api/trips", headers=h())
    assert res.status_code == 503


def test_database_error_returns_503_without_leaking_details():
    class BrokenSession:
        def scalars(self, *a, **k):
            raise OperationalError("SELECT", {}, Exception("password=secretpw"))

        def add(self, *a, **k):
            pass

        def commit(self):
            raise OperationalError("INSERT", {}, Exception("password=secretpw"))

        def rollback(self):
            pass

    app.dependency_overrides[get_db] = lambda: BrokenSession()
    try:
        c = TestClient(app)
        tid = uuid.uuid4()
        for res in (
            c.get("/api/trips", headers=h()),
            c.post("/api/trips", json={"cities": [KYOTO]}, headers=h()),
            c.get(f"/api/trips/{tid}", headers=h()),
            c.patch(f"/api/trips/{tid}", json={"title": "x"}, headers=h()),
            c.delete(f"/api/trips/{tid}", headers=h()),
        ):
            assert res.status_code == 503, res.text
            assert res.json()["detail"] == "Trip storage is unavailable."
            assert "secretpw" not in res.text
    finally:
        app.dependency_overrides.clear()


def test_failed_create_leaves_nothing_behind(client, factory, monkeypatch):
    """Trip, cities and days are written in one transaction."""
    original_flush = None

    def failing_flush(self, *args, **kwargs):
        # Fail after the trip row is staged but before commit completes.
        raise OperationalError("INSERT", {}, Exception("simulated outage"))

    from sqlalchemy.orm import Session as SASession

    original_flush = SASession.flush
    monkeypatch.setattr(SASession, "flush", failing_flush)
    res = client.post("/api/trips", json={"cities": [KYOTO, OSAKA]}, headers=h())
    monkeypatch.setattr(SASession, "flush", original_flush)
    assert res.status_code == 503
    assert counts(factory) == {"trips": 0, "trip_cities": 0, "trip_days": 0, "trip_activities": 0}


def test_dates_are_iso_and_end_date_derived(client):
    trip = create(client, start_date=date(2026, 2, 27).isoformat(), cities=[{**KYOTO, "days": 3}])
    assert trip["end_date"] == "2026-03-01"
