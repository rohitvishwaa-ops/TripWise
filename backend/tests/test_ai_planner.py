"""Optional AI layer: every Gemini call is mocked (see conftest: network is
blocked and the base URL is an unresolvable .invalid host)."""

import json
import logging
import uuid
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import ai_planner
from database import Base, TripActivity, enable_sqlite_foreign_keys, get_db
from main import app
from places import get_http_client

OWNER = str(uuid.uuid4())
GEO_KEY = "geo-key-not-real"
AI_KEY = "AIza-fake-gemini-key-for-tests-only"
KYOTO = {"name": "Kyoto", "address": "Kyoto, Japan", "latitude": 35.0, "longitude": 135.75, "days": 2}


def feature(pid, name, lat, lon, cat):
    return {"properties": {"place_id": pid, "name": name, "lat": lat, "lon": lon,
                           "formatted": f"{name}, Kyoto", "categories": [cat.split(".")[0], cat]},
            "geometry": {"coordinates": [lon, lat]}}


def geo_features(categories: str):
    """10 well-spaced places per interest query."""
    cat = categories.split(",")[0]
    tag = cat.split(".")[-1]
    base = 0.0 if "museum" in cat else 0.03
    return [feature(f"{tag}-{i}", f"{tag.title()} {i}", 35.0 + base + (i % 5) * 0.004,
                    135.75 + (i // 5) * 0.004, cat) for i in range(10)]


def gemini_ok(result) -> httpx.Response:
    text = result if isinstance(result, str) else json.dumps(result)
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]})


def first_n(per_day, num_days):
    """A valid answer: consecutive aliases, per_day per day, with themes."""
    def answer(payload):
        ids = [p["id"] for p in payload["places"]]
        return {"days": [{"place_ids": ids[d * per_day:(d + 1) * per_day], "theme": f"Theme {chr(65 + d)}"}
                         for d in range(num_days)]}
    return answer


@pytest.fixture
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def mock(monkeypatch):
    """Routes Geoapify and Gemini requests to fakes; records Gemini requests."""
    monkeypatch.setenv("GEOAPIFY_API_KEY", GEO_KEY)
    state = {"gemini": None, "gemini_calls": [], "geo_calls": 0}

    def transport(request: httpx.Request):
        host = request.url.host
        if host == "api.geoapify.com":
            state["geo_calls"] += 1
            cats = parse_qs(urlparse(str(request.url)).query)["categories"][0]
            return httpx.Response(200, json={"features": geo_features(cats)})
        if host == "gemini.test.invalid":
            body = json.loads(request.content)
            payload = json.loads(body["contents"][0]["parts"][0]["text"])
            state["gemini_calls"].append({"request": request, "body": body, "payload": payload})
            handler = state["gemini"]
            if handler is None:
                raise AssertionError("unexpected Gemini call")
            out = handler(payload, request)
            return out if isinstance(out, httpx.Response) else gemini_ok(out)
        raise AssertionError(f"unexpected host {host}")

    async def override():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as c:
            yield c

    app.dependency_overrides[get_http_client] = override
    yield state
    app.dependency_overrides.pop(get_http_client, None)


@pytest.fixture
def client(factory, mock):
    def override_get_db():
        with factory() as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def ai_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", AI_KEY)


def generate(client, planner="ai", **extra):
    body = {"title": "Secret title", "cities": [KYOTO], "generate": True, "planner": planner,
            "pace": "balanced", "interests": ["culture", "food"], **extra}
    res = client.post("/api/trips", json=body, headers={"X-Trip-ID": OWNER})
    assert res.status_code == 201, res.text
    return res.json()


def is_auto(trip):
    return trip["planner"] == "auto" and all(
        d["generated_by"] == "auto" and all(a["source"] == "auto" for a in d["activities"]) for d in trip["days"])


# --- Status ---------------------------------------------------------------------


def test_status_without_key(client):
    assert client.get("/api/planner/status").json() == {"ai_available": False, "default_planner": "auto"}


def test_status_with_key_never_returns_it(client, ai_key):
    res = client.get("/api/planner/status")
    assert res.json()["ai_available"] is True
    assert AI_KEY not in res.text


@pytest.mark.parametrize("model", ["../../evil", "Gemini Flash", "x" * 80, "model/with/slash"])
def test_status_rejects_unsafe_model_names(client, ai_key, monkeypatch, model):
    monkeypatch.setenv("GEMINI_MODEL", model)
    assert client.get("/api/planner/status").json()["ai_available"] is False


# --- Valid AI output -------------------------------------------------------------


def test_valid_ai_plan_is_used(client, mock, ai_key):
    mock["gemini"] = lambda payload, req: first_n(3, 2)(payload)
    trip = generate(client)
    assert trip["planner"] == "ai" and trip["warnings"] == []
    assert [d["theme"] for d in trip["days"]] == ["Theme A", "Theme B"]
    for d in trip["days"]:
        assert d["generated_by"] == "ai"
        assert len(d["activities"]) == 3
        assert [a["slot"] for a in d["activities"]] == ["morning", "afternoon", "evening"]
        assert all(a["source"] == "ai" and a["place_id"] for a in d["activities"])
    ids = [a["place_id"] for d in trip["days"] for a in d["activities"]]
    assert len(ids) == len(set(ids))
    # The chosen places are exactly the first six aliases, mapped back to real places.
    sent = mock["gemini_calls"][0]["payload"]["places"]
    chosen_names = {p["name"] for p in sent[:6]}
    assert {a["name"] for d in trip["days"] for a in d["activities"]} == chosen_names
    assert len(mock["gemini_calls"]) == 1


def test_request_shape_and_minimal_data(client, mock, ai_key, monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    mock["gemini"] = lambda payload, req: first_n(3, 2)(payload)
    generate(client)
    call = mock["gemini_calls"][0]
    req, body, payload = call["request"], call["body"], call["payload"]
    assert req.method == "POST"
    assert req.url.path == "/v1beta/models/gemini-3.5-flash-lite:generateContent"
    assert req.headers["x-goog-api-key"] == AI_KEY
    assert AI_KEY not in str(req.url)  # key only in a header
    assert set(payload) == {"city", "days", "max_stops_per_day", "interests", "places"}
    assert payload["days"] == 2 and payload["max_stops_per_day"] == 3
    assert 1 <= len(payload["places"]) <= ai_planner.MAX_CANDIDATES
    for p in payload["places"]:
        assert set(p) == {"id", "name", "category", "interest", "lat", "lon"}
        assert p["id"].startswith("p")  # opaque alias, not the real place id
    raw = json.dumps(body)
    for secret in ("Secret title", OWNER, GEO_KEY, AI_KEY, "museum-0"):
        assert secret not in raw  # no title, browser id, keys or real place ids
    gc = body["generationConfig"]
    assert gc["responseMimeType"] == "application/json"
    assert gc["maxOutputTokens"] <= 1024
    enum = gc["responseSchema"]["properties"]["days"]["items"]["properties"]["place_ids"]["items"]["enum"]
    assert enum == [p["id"] for p in payload["places"]]


def test_server_orders_each_day_regardless_of_ai_order(client, mock, ai_key):
    def answer(payload, req):
        # Give each day's ids farthest-first from the city centre.
        places = sorted(payload["places"], key=lambda p: -abs(p["lat"] - 35.0) - abs(p["lon"] - 135.75))
        ids = [p["id"] for p in places]
        return {"days": [{"place_ids": ids[:3]}, {"place_ids": ids[3:6]}]}

    mock["gemini"] = answer
    trip = generate(client)
    assert trip["planner"] == "ai"
    for d in trip["days"]:
        dist = [abs(a["latitude"] - 35.0) + abs(a["longitude"] - 135.75) for a in d["activities"]]
        assert dist[0] == min(dist)  # nearest-first from the centre, decided by the server
        assert d["theme"]  # automatic theme when the AI gives none


def test_fewer_stops_than_pace_is_allowed_with_warning(client, mock, ai_key):
    mock["gemini"] = lambda payload, req: {"days": [{"place_ids": ["p1", "p2"]}, {"place_ids": ["p3"]}]}
    trip = generate(client)
    assert trip["planner"] == "ai"
    assert [len(d["activities"]) for d in trip["days"]] == [2, 1]
    assert "The AI chose 3 places" in trip["warnings"][0]


# --- Invalid output -> automatic fallback with warning ----------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        {"days": [{"place_ids": ["p1", "p2", "p999"]}, {"place_ids": ["p3"]}]},  # unknown id
        {"days": [{"place_ids": ["p1", "p1"]}, {"place_ids": ["p2"]}]},  # duplicate in a day
        {"days": [{"place_ids": ["p1", "p2"]}, {"place_ids": ["p2", "p3"]}]},  # duplicate across days
        {"days": [{"place_ids": ["p1", "p2", "p3"]}]},  # too few days
        {"days": [{"place_ids": ["p1"]}, {"place_ids": ["p2"]}, {"place_ids": ["p3"]}]},  # too many days
        {"days": [{"place_ids": []}, {"place_ids": ["p2"]}]},  # empty day
        {"days": [{"place_ids": ["p1", "p2", "p3", "p4"]}, {"place_ids": ["p5"]}]},  # over pace
        {"days": [{"place_ids": "p1,p2"}, {"place_ids": ["p3"]}]},  # not a list
        {"days": [{"place_ids": [1, 2]}, {"place_ids": ["p3"]}]},  # not strings
        {"days": [["p1"], ["p2"]]},  # day not an object
        {"days": "two"},
        {"itinerary": []},
        ["p1", "p2"],
        "not json at all",
        '{"days": [{"place_ids": ["p1"]',  # truncated JSON
    ],
)
def test_invalid_ai_output_falls_back(client, mock, ai_key, answer):
    mock["gemini"] = lambda payload, req: answer
    trip = generate(client)
    assert is_auto(trip)
    assert trip["warnings"][0] == ai_planner.FALLBACK_WARNING
    assert sum(len(d["activities"]) for d in trip["days"]) == 6


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>oops</html>"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={"candidates": []}),
        httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}),
        httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"days": ['}]}, "finishReason": "MAX_TOKENS"}]}),
        httpx.Response(200, json={"candidates": [{"content": {"parts": []}, "finishReason": "STOP"}]}),
    ],
)
def test_malformed_envelopes_fall_back(client, mock, ai_key, response):
    mock["gemini"] = lambda payload, req: response
    trip = generate(client)
    assert is_auto(trip) and trip["warnings"][0] == ai_planner.FALLBACK_WARNING


@pytest.mark.parametrize(
    "theme",
    ["Museums from 9am", "Open until 18:00", "Cheap eats", "Free entry museums", "Day 1 highlights",
     "10 minute walk", "Tickets and tours", "Under $20", "x" * 61, "a b c d e f g h i", "", "   ", 42],
)
def test_invalid_themes_are_replaced_not_trusted(client, mock, ai_key, theme):
    def answer(payload, req):
        ids = [p["id"] for p in payload["places"]]
        return {"days": [{"place_ids": ids[:3], "theme": theme}, {"place_ids": ids[3:6], "theme": "Museums and gardens"}]}

    mock["gemini"] = answer
    trip = generate(client)
    assert trip["planner"] == "ai"  # plan kept, only the theme is replaced
    assert trip["days"][0]["theme"] != theme and trip["days"][0]["theme"]
    assert trip["days"][1]["theme"] == "Museums and gardens"


# --- Service failures -> automatic fallback ---------------------------------------------


def test_timeout_falls_back(client, mock, ai_key):
    def boom(payload, req):
        raise httpx.ReadTimeout("slow", request=req)

    mock["gemini"] = boom
    trip = generate(client)
    assert is_auto(trip) and trip["warnings"][0] == ai_planner.FALLBACK_WARNING


def test_connection_error_falls_back(client, mock, ai_key):
    def boom(payload, req):
        raise httpx.ConnectError("down", request=req)

    mock["gemini"] = boom
    assert is_auto(generate(client))


@pytest.mark.parametrize("status", [400, 401, 403, 404, 500, 503])
def test_error_statuses_fall_back(client, mock, ai_key, status):
    mock["gemini"] = lambda payload, req: httpx.Response(status, json={"error": {"message": f"bad key {AI_KEY}"}})
    trip = generate(client)
    assert is_auto(trip) and trip["warnings"][0] == ai_planner.FALLBACK_WARNING
    assert AI_KEY not in json.dumps(trip)


def test_rate_limit_falls_back_and_cools_down(client, mock, ai_key):
    mock["gemini"] = lambda payload, req: httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED"}})
    assert is_auto(generate(client))
    assert len(mock["gemini_calls"]) == 1
    # During the cooldown the AI is not called again, even if it would succeed.
    mock["gemini"] = lambda payload, req: first_n(3, 2)(payload)
    trip = generate(client)
    assert is_auto(trip) and trip["warnings"][0] == ai_planner.FALLBACK_WARNING
    assert len(mock["gemini_calls"]) == 1


def test_missing_key_falls_back_without_calling(client, mock):
    trip = generate(client)
    assert is_auto(trip)
    assert trip["warnings"][0] == ai_planner.NOT_CONFIGURED_WARNING
    assert mock["gemini_calls"] == []


def test_auto_planner_never_calls_ai_even_with_key(client, mock, ai_key):
    trip = generate(client, planner="auto")
    assert is_auto(trip) and trip["warnings"] == []
    assert mock["gemini_calls"] == []


def test_default_planner_is_auto(client, mock, ai_key):
    res = client.post("/api/trips", json={"cities": [KYOTO], "generate": True}, headers={"X-Trip-ID": OWNER})
    assert res.json()["planner"] == "auto" and mock["gemini_calls"] == []


@pytest.mark.parametrize("body", [
    {"cities": [KYOTO], "planner": "ai"},  # without generate
    {"cities": [KYOTO], "generate": True, "planner": "gpt"},
])
def test_planner_validation(client, body):
    assert client.post("/api/trips", json=body, headers={"X-Trip-ID": OWNER}).status_code == 422


def test_geoapify_failure_still_fails_cleanly_with_ai(client, mock, ai_key, factory):
    def fail_geo(request):
        return httpx.Response(500)

    # Replace Geoapify with a failing endpoint: no AI call, nothing saved.
    original = app.dependency_overrides[get_http_client]

    async def override():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fail_geo)) as c:
            yield c

    app.dependency_overrides[get_http_client] = override
    res = client.post("/api/trips", json={"cities": [KYOTO], "generate": True, "planner": "ai"},
                      headers={"X-Trip-ID": OWNER})
    app.dependency_overrides[get_http_client] = original
    assert res.status_code == 502
    assert mock["gemini_calls"] == []


# --- Regenerating one day with AI --------------------------------------------------------


def make_auto_trip(client):
    trip = generate(client, planner="auto")
    assert trip["planner"] == "auto"
    return trip


def test_regenerate_day_with_ai_changes_only_that_day(client, mock, ai_key):
    trip = make_auto_trip(client)
    day0, day1 = trip["days"]
    other_names = {a["name"] for a in day1["activities"]}

    def answer(payload, req):
        assert payload["days"] == 1
        sent = {p["name"] for p in payload["places"]}
        assert not (sent & other_names)  # other days' places are never offered
        ids = [p["id"] for p in payload["places"]]
        return {"days": [{"place_ids": ids[:3], "theme": "Gardens and cafes"}]}

    mock["gemini"] = answer
    res = client.post(f"/api/trips/{trip['id']}/days/{day0['id']}/regenerate", json={"planner": "ai"},
                      headers={"X-Trip-ID": OWNER})
    assert res.status_code == 200, res.text
    new0, new1 = res.json()["days"]
    assert new1 == day1  # untouched
    assert new0["generated_by"] == "ai" and new0["theme"] == "Gardens and cafes"
    assert all(a["source"] == "ai" for a in new0["activities"])
    ids = [a["place_id"] for d in res.json()["days"] for a in d["activities"]]
    assert len(ids) == len(set(ids))


def test_regenerate_ai_failure_falls_back_and_keeps_other_days(client, mock, ai_key):
    trip = make_auto_trip(client)
    day0, day1 = trip["days"]
    mock["gemini"] = lambda payload, req: {"days": [{"place_ids": ["p999"]}]}
    res = client.post(f"/api/trips/{trip['id']}/days/{day0['id']}/regenerate", json={"planner": "ai"},
                      headers={"X-Trip-ID": OWNER})
    assert res.status_code == 200
    body = res.json()
    assert body["days"][1] == day1
    assert body["days"][0]["generated_by"] == "auto"
    assert body["warnings"][0] == ai_planner.FALLBACK_WARNING


def test_regenerate_without_body_stays_automatic(client, mock, ai_key):
    trip = make_auto_trip(client)
    res = client.post(f"/api/trips/{trip['id']}/days/{trip['days'][0]['id']}/regenerate", headers={"X-Trip-ID": OWNER})
    assert res.status_code == 200 and mock["gemini_calls"] == []


def test_regenerate_body_validation(client, mock, ai_key):
    trip = make_auto_trip(client)
    url = f"/api/trips/{trip['id']}/days/{trip['days'][0]['id']}/regenerate"
    assert client.post(url, json={"planner": "magic"}, headers={"X-Trip-ID": OWNER}).status_code == 422
    assert client.post(url, json={"planner": "ai", "extra": 1}, headers={"X-Trip-ID": OWNER}).status_code == 422


def test_regenerate_ai_missing_key_warns(client, mock):
    trip = make_auto_trip(client)
    res = client.post(f"/api/trips/{trip['id']}/days/{trip['days'][0]['id']}/regenerate", json={"planner": "ai"},
                      headers={"X-Trip-ID": OWNER})
    assert res.json()["warnings"][0] == ai_planner.NOT_CONFIGURED_WARNING
    assert mock["gemini_calls"] == []


# --- Secrets never leak ------------------------------------------------------------------


def test_keys_never_in_responses_or_logs(client, mock, ai_key, caplog):
    caplog.set_level(logging.DEBUG)
    responses = []
    mock["gemini"] = lambda payload, req: first_n(3, 2)(payload)
    responses.append(client.post("/api/trips", json={"cities": [KYOTO], "generate": True, "planner": "ai"},
                                  headers={"X-Trip-ID": OWNER}))
    mock["gemini"] = lambda payload, req: httpx.Response(500, json={"error": {"message": AI_KEY}})
    responses.append(client.post("/api/trips", json={"cities": [KYOTO], "generate": True, "planner": "ai"},
                                 headers={"X-Trip-ID": OWNER}))
    mock["gemini"] = lambda payload, req: f"key is {AI_KEY}"
    responses.append(client.post("/api/trips", json={"cities": [KYOTO], "generate": True, "planner": "ai"},
                                 headers={"X-Trip-ID": OWNER}))
    responses.append(client.get("/api/planner/status"))
    for res in responses:
        assert AI_KEY not in res.text and GEO_KEY not in res.text
    assert AI_KEY not in caplog.text and GEO_KEY not in caplog.text
    assert "AI planner not used" in caplog.text  # failures are logged, without secrets


# --- Isolation: the real service is unreachable from tests ------------------------------


def test_real_gemini_is_unreachable_from_tests(ai_key):
    """Even a real HTTP client cannot reach Gemini: the URL is a reserved
    .invalid host and outbound sockets are blocked (see conftest)."""
    import asyncio

    async def attempt():
        async with httpx.AsyncClient() as real_client:
            body, _ = ai_planner.build_request("Kyoto", [], 1, 2, [])
            with pytest.raises(ai_planner.AIUnavailable):
                await ai_planner._call(real_client, ai_planner.get_config(), body)

    asyncio.run(attempt())
    assert "gemini.test.invalid" in ai_planner.GEMINI_BASE_URL


# --- Unit: theme and validation -----------------------------------------------------------


def test_clean_theme():
    assert ai_planner.clean_theme("  Museums   and gardens ") == "Museums and gardens"
    assert ai_planner.clean_theme("Temples, tea and markets") == "Temples, tea and markets"
    for bad in ("Lunch at 1pm", "₹500 street food", "2 parks", "Short drive to lakes", None, ["x"]):
        assert ai_planner.clean_theme(bad) is None


def test_activity_rows_store_ai_source(client, mock, ai_key, factory):
    mock["gemini"] = lambda payload, req: first_n(3, 2)(payload)
    generate(client)
    from sqlalchemy import select
    with factory() as s:
        assert {a.source for a in s.scalars(select(TripActivity))} == {"ai"}
