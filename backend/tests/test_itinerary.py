import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
from database import Base, ItineraryItem, build_database_url, get_db, init_db
from main import app

TRIP_A = str(uuid.uuid4())
TRIP_B = str(uuid.uuid4())

PLACE = {
    "id": "51a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c3d5e7f9",
    "name": "Louvre Museum",
    "address": "Rue de Rivoli, 75001 Paris, France",
    "latitude": 48.8606,
    "longitude": 2.3376,
    "categories": ["entertainment", "entertainment.museum"],
}
OTHER = {**PLACE, "id": "p2", "name": "Eiffel Tower", "latitude": 48.8584, "longitude": 2.2945}


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def client(engine):
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def headers(trip=TRIP_A):
    return {"X-Trip-ID": trip}


# --- happy paths ---------------------------------------------------------


def test_empty_itinerary(client):
    res = client.get("/api/itinerary", headers=headers())
    assert res.status_code == 200
    assert res.json() == {"trip_id": TRIP_A, "count": 0, "places": []}


def test_add_and_list(client):
    res = client.post("/api/itinerary", json=PLACE, headers=headers())
    assert res.status_code == 201
    body = res.json()
    assert {k: body[k] for k in PLACE} == PLACE
    assert "added_at" in body

    client.post("/api/itinerary", json=OTHER, headers=headers())
    listed = client.get("/api/itinerary", headers=headers()).json()
    assert listed["count"] == 2
    assert [p["id"] for p in listed["places"]] == [PLACE["id"], "p2"]


def test_accepts_place_from_places_api_with_minimal_fields(client):
    res = client.post(
        "/api/itinerary",
        json={"id": "p9", "latitude": 1, "longitude": 2},
        headers=headers(),
    )
    assert res.status_code == 201
    assert res.json()["name"] is None
    assert res.json()["categories"] == []


def test_delete(client):
    client.post("/api/itinerary", json=PLACE, headers=headers())
    res = client.delete(f"/api/itinerary/{PLACE['id']}", headers=headers())
    assert res.status_code == 204
    assert res.content == b""
    assert client.get("/api/itinerary", headers=headers()).json()["count"] == 0


def test_trip_id_is_case_insensitive(client):
    client.post("/api/itinerary", json=PLACE, headers=headers(TRIP_A.upper()))
    assert client.get("/api/itinerary", headers=headers(TRIP_A)).json()["count"] == 1


# --- trip scoping --------------------------------------------------------


def test_trips_are_isolated(client):
    client.post("/api/itinerary", json=PLACE, headers=headers(TRIP_A))
    assert client.get("/api/itinerary", headers=headers(TRIP_B)).json()["count"] == 0
    # Another trip cannot delete A's item.
    res = client.delete(f"/api/itinerary/{PLACE['id']}", headers=headers(TRIP_B))
    assert res.status_code == 404
    assert client.get("/api/itinerary", headers=headers(TRIP_A)).json()["count"] == 1


def test_same_place_allowed_in_different_trips(client):
    assert client.post("/api/itinerary", json=PLACE, headers=headers(TRIP_A)).status_code == 201
    assert client.post("/api/itinerary", json=PLACE, headers=headers(TRIP_B)).status_code == 201


# --- errors --------------------------------------------------------------


def test_duplicate_place_rejected(client):
    client.post("/api/itinerary", json=PLACE, headers=headers())
    res = client.post("/api/itinerary", json=PLACE, headers=headers())
    assert res.status_code == 409
    assert "already" in res.json()["detail"]
    assert client.get("/api/itinerary", headers=headers()).json()["count"] == 1


def test_unique_constraint_enforced_at_db_level(engine):
    factory = sessionmaker(bind=engine)
    with factory() as s:
        s.add(ItineraryItem(trip_id=TRIP_A, place_id="x", latitude=0, longitude=0, categories=[]))
        s.commit()
        s.add(ItineraryItem(trip_id=TRIP_A, place_id="x", latitude=0, longitude=0, categories=[]))
        with pytest.raises(Exception):
            s.commit()


def test_delete_missing_item(client):
    res = client.delete("/api/itinerary/does-not-exist", headers=headers())
    assert res.status_code == 404
    assert "not found" in res.json()["detail"]


@pytest.mark.parametrize("method", ["get", "post", "delete"])
def test_missing_trip_id(client, method):
    url = "/api/itinerary/p1" if method == "delete" else "/api/itinerary"
    kwargs = {"json": PLACE} if method == "post" else {}
    res = getattr(client, method)(url, **kwargs)
    assert res.status_code == 400
    assert "X-Trip-ID" in res.json()["detail"]


@pytest.mark.parametrize(
    "trip_id",
    [
        "abc",
        "not-a-uuid-at-all-0000000000000000000",
        "12345678123456781234567812345678",  # hex without dashes
        "{" + TRIP_A + "}",
        "urn:uuid:" + TRIP_A,
        TRIP_A + "0",
        "' OR 1=1 --",
    ],
)
def test_invalid_trip_id(client, trip_id):
    res = client.get("/api/itinerary", headers=headers(trip_id))
    assert res.status_code == 400


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {k: v for k, v in PLACE.items() if k != "id"},
        {k: v for k, v in PLACE.items() if k != "latitude"},
        {**PLACE, "id": ""},
        {**PLACE, "id": "bad id/with slash"},
        {**PLACE, "id": "x" * 513},
        {**PLACE, "latitude": 91},
        {**PLACE, "longitude": -181},
        {**PLACE, "latitude": "north"},
        {**PLACE, "name": "n" * 501},
        {**PLACE, "address": "a" * 1001},
        {**PLACE, "categories": "tourism"},
        {**PLACE, "categories": [""]},
        {**PLACE, "categories": ["c" * 101]},
        {**PLACE, "categories": [f"c{i}" for i in range(51)]},
    ],
)
def test_invalid_place_payload(client, payload):
    res = client.post("/api/itinerary", json=payload, headers=headers())
    assert res.status_code == 422
    assert client.get("/api/itinerary", headers=headers()).json()["count"] == 0


def test_invalid_place_id_in_path(client):
    res = client.delete("/api/itinerary/bad%20id", headers=headers())
    assert res.status_code == 422


# --- configuration / availability ---------------------------------------


def test_not_configured_returns_503():
    # No override: real get_db with DATABASE_URL removed by conftest.
    res = TestClient(app).get("/api/itinerary", headers=headers())
    assert res.status_code == 503
    assert "not configured" in res.json()["detail"]


def test_malformed_database_url_returns_503(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "not a url://user:secretpw@")
    res = TestClient(app).get("/api/itinerary", headers=headers())
    assert res.status_code == 503
    assert "secretpw" not in res.text


def test_database_error_returns_503():
    class BrokenSession:
        def scalars(self, *a, **k):
            raise OperationalError("SELECT", {}, Exception("conn refused password=secretpw"))

        def rollback(self):
            pass

    app.dependency_overrides[get_db] = lambda: BrokenSession()
    try:
        client = TestClient(app)
        for res in (
            client.get("/api/itinerary", headers=headers()),
            client.post("/api/itinerary", json=PLACE, headers=headers()),
            client.delete("/api/itinerary/p1", headers=headers()),
        ):
            assert res.status_code == 503
            assert "secretpw" not in res.text
    finally:
        app.dependency_overrides.clear()


def test_init_db_creates_tables_without_dropping(monkeypatch, tmp_path):
    db_file = tmp_path / "trip.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")

    init_db()
    factory = sessionmaker(bind=database.get_engine())
    with factory() as s:
        s.add(ItineraryItem(trip_id=TRIP_A, place_id="keep", latitude=0, longitude=0, categories=[]))
        s.commit()

    init_db()  # second startup must keep existing data
    assert "itinerary_items" in inspect(database.get_engine()).get_table_names()
    with factory() as s:
        assert s.query(ItineraryItem).count() == 1
    database.get_engine().dispose()


def test_init_db_without_url_is_noop():
    init_db()  # must not raise
    assert database.get_engine() is None


def test_init_db_survives_unreachable_database(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/none?connect_timeout=1")
    init_db()  # logs, does not raise


# --- URL handling --------------------------------------------------------


def test_url_uses_psycopg_and_requires_ssl_for_remote():
    url = build_database_url("postgresql://u:p@ep-x.neon.tech/db")
    assert url.drivername == "postgresql+psycopg"
    assert url.query["sslmode"] == "require"


def test_url_postgres_scheme_alias():
    assert build_database_url("postgres://u:p@h.example/db").drivername == "postgresql+psycopg"


def test_url_keeps_explicit_ssl_settings():
    url = build_database_url(
        "postgresql://u:p@ep-x.neon.tech/db?sslmode=verify-full&channel_binding=require"
    )
    assert url.query["sslmode"] == "verify-full"
    assert url.query["channel_binding"] == "require"


def test_url_local_postgres_no_forced_ssl():
    assert "sslmode" not in build_database_url("postgresql://u:p@localhost/db").query


def test_health_unaffected_without_database():
    assert TestClient(app).get("/health").json() == {"status": "ok"}
