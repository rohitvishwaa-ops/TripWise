import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import auth
from database import Base, ItineraryItem, Trip, enable_sqlite_foreign_keys, get_db
from main import app

GUEST = str(uuid.uuid4())


@pytest.fixture
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    engine.dispose()


@pytest.fixture
def client(factory):
    def override_get_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_valid_token_checks_project_issuer_and_audience(monkeypatch):
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "tripwise-test")
    monkeypatch.setattr(auth, "_firebase_app", lambda: object())
    monkeypatch.setattr(auth.firebase_auth, "verify_id_token", lambda token, app: {
        "uid": "firebase-user-a",
        "iss": "https://securetoken.google.com/tripwise-test",
        "aud": "tripwise-test",
        "email_verified": True,
        "email": "a@example.test",
    })
    identity = auth.verify_firebase_token("valid")
    assert identity.uid == "firebase-user-a"
    assert identity.owner_id == auth.owner_id_for_uid("firebase-user-a")


@pytest.mark.parametrize("claims", [
    {"uid": "u", "iss": "https://securetoken.google.com/wrong", "aud": "tripwise-test"},
    {"uid": "u", "iss": "https://securetoken.google.com/tripwise-test", "aud": "wrong"},
    {"uid": "u", "iss": "https://securetoken.google.com/tripwise-test"},
])
def test_wrong_project_or_audience_is_rejected(monkeypatch, claims):
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "tripwise-test")
    monkeypatch.setattr(auth, "_firebase_app", lambda: object())
    monkeypatch.setattr(auth.firebase_auth, "verify_id_token", lambda token, app: claims)
    with pytest.raises(HTTPException) as exc:
        auth.verify_firebase_token("invalid")
    assert exc.value.status_code == 401


def test_expired_token_is_rejected(monkeypatch):
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "tripwise-test")
    monkeypatch.setattr(auth, "_firebase_app", lambda: object())
    monkeypatch.setattr(auth.firebase_auth, "verify_id_token", lambda token, app: (_ for _ in ()).throw(
        auth.firebase_auth.ExpiredIdTokenError("expired", None)
    ))
    with pytest.raises(HTTPException) as exc:
        auth.verify_firebase_token("expired")
    assert exc.value.status_code == 401


def test_unverified_email_is_not_authorized(monkeypatch):
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "tripwise-test")
    monkeypatch.setattr(auth, "_firebase_app", lambda: object())
    monkeypatch.setattr(auth.firebase_auth, "verify_id_token", lambda token, app: {
        "uid": "unverified", "iss": "https://securetoken.google.com/tripwise-test",
        "aud": "tripwise-test", "email_verified": False,
    })
    with pytest.raises(HTTPException) as exc:
        auth.verify_firebase_token("valid-but-unverified")
    assert exc.value.status_code == 403


def test_guest_header_still_works_without_bearer(client):
    response = client.get("/api/itinerary", headers={"X-Trip-ID": GUEST})
    assert response.status_code == 200
    assert response.json()["trip_id"] == GUEST


def test_invalid_bearer_never_falls_back_to_forged_guest_id(client, monkeypatch):
    def reject(_token):
        raise HTTPException(status_code=401, detail="Invalid authentication token.")

    monkeypatch.setattr(auth, "verify_firebase_token", reject)
    response = client.get(
        "/api/itinerary",
        headers={"Authorization": "Bearer forged", "X-Trip-ID": GUEST},
    )
    assert response.status_code == 401


def test_authenticated_owner_ignores_client_owner_id(client, factory, monkeypatch):
    uid = "firebase-user-a"
    owner = auth.owner_id_for_uid(uid)
    with factory() as db:
        db.add(ItineraryItem(
            trip_id=owner, place_id="auth-place", name="Verified place",
            latitude=1, longitude=2, categories=[],
        ))
        db.commit()
    monkeypatch.setattr(auth, "verify_firebase_token", lambda _token: auth.AuthIdentity(uid, owner))
    response = client.get(
        "/api/itinerary",
        headers={"Authorization": "Bearer valid", "X-Trip-ID": GUEST},
    )
    assert response.status_code == 200
    assert [place["id"] for place in response.json()["places"]] == ["auth-place"]


def test_different_verified_uids_cannot_read_each_other(client, factory, monkeypatch):
    owner_a = auth.owner_id_for_uid("firebase-a")
    with factory() as db:
        db.add(ItineraryItem(
            trip_id=owner_a, place_id="private", name="Private",
            latitude=1, longitude=2, categories=[],
        ))
        db.commit()
    monkeypatch.setattr(auth, "verify_firebase_token", lambda _token: auth.AuthIdentity(
        "firebase-b", auth.owner_id_for_uid("firebase-b")
    ))
    response = client.get("/api/itinerary", headers={"Authorization": "Bearer b", "X-Trip-ID": owner_a})
    assert response.status_code == 200
    assert response.json()["places"] == []


def test_authenticated_trip_creation_ignores_forged_owner_header(client, factory, monkeypatch):
    uid = "firebase-trip-owner"
    owner = auth.owner_id_for_uid(uid)
    monkeypatch.setattr(auth, "verify_firebase_token", lambda _token: auth.AuthIdentity(uid, owner))
    response = client.post(
        "/api/trips",
        json={"cities": [{"name": "Kyoto", "latitude": 35.01, "longitude": 135.76, "days": 1}]},
        headers={"Authorization": "Bearer valid", "X-Trip-ID": GUEST},
    )
    assert response.status_code == 201
    trip_id = response.json()["id"]
    with factory() as db:
        assert db.scalar(select(Trip.owner_id).where(Trip.id == trip_id)) == owner
    monkeypatch.setattr(auth, "verify_firebase_token", lambda _token: auth.AuthIdentity(
        "firebase-other", auth.owner_id_for_uid("firebase-other")
    ))
    forbidden = client.get(f"/api/trips/{trip_id}", headers={"Authorization": "Bearer other", "X-Trip-ID": owner})
    assert forbidden.status_code == 404


def test_auth_account_schema_can_be_rolled_back_without_trip_tables(factory):
    with factory() as db:
        db.execute(text(
            "CREATE TABLE auth_accounts (id VARCHAR(36) PRIMARY KEY, "
            "firebase_uid VARCHAR(128) UNIQUE NOT NULL, workspace_id VARCHAR(36) UNIQUE NOT NULL, "
            "email VARCHAR(320))"
        ))
        db.commit()
        assert inspect(db.bind).has_table("auth_accounts")
        db.execute(text("DROP TABLE auth_accounts"))
        db.commit()
        assert not inspect(db.bind).has_table("auth_accounts")
        assert inspect(db.bind).has_table("trips")
