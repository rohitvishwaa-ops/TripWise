"""Location-name search (city, landmark, address) via the Geoapify Geocoding API."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api_docs import errors
from places import geoapify_get, get_api_key, get_http_client

GEOAPIFY_GEOCODE_URL = "https://api.geoapify.com/v1/geocode/search"
MIN_QUERY_LENGTH = 2
MAX_QUERY_LENGTH = 200

# A result is only treated as "the" answer when it is a strong match and no
# other result comes close; otherwise the client must ask the user to choose.
CONFIDENT_MIN = 0.9
RUNNER_UP_MAX = 0.6

router = APIRouter(prefix="/api", tags=["geocode"])


class Location(BaseModel):
    id: str | None = None
    name: str
    address: str | None = None
    latitude: float
    longitude: float
    type: str | None = None
    country: str | None = None
    confidence: float | None = None


class GeocodeResponse(BaseModel):
    query: str
    count: int
    confident: bool
    results: list[Location]


def normalize_result(result: dict) -> Location | None:
    lat, lon = result.get("lat"), result.get("lon")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
    formatted = result.get("formatted")
    name = (
        result.get("name")
        or result.get("address_line1")
        or result.get("city")
        or formatted
    )
    if not name:
        return None
    rank = result.get("rank") if isinstance(result.get("rank"), dict) else {}
    confidence = rank.get("confidence")
    return Location(
        id=result.get("place_id"),
        name=name,
        address=formatted,
        latitude=lat,
        longitude=lon,
        type=result.get("result_type"),
        country=result.get("country"),
        confidence=confidence if isinstance(confidence, (int, float)) else None,
    )


def is_confident(results: list[Location]) -> bool:
    if not results:
        return False
    top = results[0].confidence or 0.0
    runner_up = (results[1].confidence or 0.0) if len(results) > 1 else 0.0
    return top >= CONFIDENT_MIN and runner_up < RUNNER_UP_MAX


@router.get(
    "/geocode",
    response_model=GeocodeResponse,
    responses=errors(400, 502, 503, 504, d400="The location search provider rejected the request."),
)
async def geocode(
    text: str = Query(
        ...,
        max_length=MAX_QUERY_LENGTH,
        description="City, place or address, e.g. 'Lisbon' or 'Central Park, New York'",
    ),
    limit: int = Query(5, ge=1, le=10),
    api_key: str = Depends(get_api_key),
    client: httpx.AsyncClient = Depends(get_http_client),
):
    query = " ".join(text.split())
    if len(query) < MIN_QUERY_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Enter at least {MIN_QUERY_LENGTH} characters to search for a location.",
        )

    data = await geoapify_get(
        client,
        GEOAPIFY_GEOCODE_URL,
        {"text": query, "format": "json", "limit": limit, "lang": "en", "apiKey": api_key},
        provider="Location search provider",
        bad_request_detail="Location search provider rejected the request.",
    )

    raw = data.get("results")
    if not isinstance(raw, list):
        raise HTTPException(
            status_code=502, detail="Invalid response from location search provider."
        )

    results: list[Location] = []
    seen: set[tuple] = set()
    for item in raw:
        location = normalize_result(item) if isinstance(item, dict) else None
        if location is None:
            continue
        key = (location.address, round(location.latitude, 4), round(location.longitude, 4))
        if key in seen:
            continue
        seen.add(key)
        results.append(location)

    return GeocodeResponse(
        query=query,
        count=len(results),
        confident=is_confident(results),
        results=results,
    )
