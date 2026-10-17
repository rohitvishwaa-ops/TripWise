"""Destination discovery backed by the Geoapify Places API."""

import logging
import os
import re
import unicodedata
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from api_docs import errors

logger = logging.getLogger(__name__)

# httpx logs every request URL at INFO level. Geoapify only accepts its key as
# a URL parameter (apiKey=...), so request logging would leak the key into
# server logs. Keep httpx/httpcore quiet below WARNING.
for _noisy in ("httpx", "httpcore"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

GEOAPIFY_PLACES_URL = "https://api.geoapify.com/v2/places"
DEFAULT_CATEGORIES = "tourism.attraction,tourism.sights,heritage,leisure.park,natural"
MAX_CATEGORIES = 20
CATEGORY_PATTERN = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)*$")
REQUEST_TIMEOUT = httpx.Timeout(10.0)

router = APIRouter(prefix="/api", tags=["places"])


class Place(BaseModel):
    id: str | None = None
    name: str | None = None
    address: str | None = None
    latitude: float
    longitude: float
    categories: list[str] = []


class PlacesResponse(BaseModel):
    count: int
    places: list[Place]


GENERIC_NAMES = {
    "artwork",
    "attraction",
    "landmark",
    "monument",
    "point of interest",
    "poi",
    "place of interest",
    "sculpture",
    "statue",
    "tourist attraction",
    "unknown",
    "unnamed",
    "unnamed attraction",
    "untitled",
}
IRRELEVANT_NAME_PARTS = (
    "supermarket",
    "pharmacy",
    "restaurant",
    "cafe",
    "hotel",
    "salon",
)


def is_useful_place(place: Place) -> bool:
    name = " ".join((place.name or "").split()).strip()
    if not name:
        return False
    normalized = re.sub(r"[^a-z0-9 ]+", " ", name.casefold()).strip()
    if normalized in GENERIC_NAMES or normalized.startswith("unnamed "):
        return False
    if any(part in normalized for part in IRRELEVANT_NAME_PARTS):
        return False
    return True


def filter_places(places: list[Place], limit: int) -> list[Place]:
    useful: list[Place] = []
    seen: set[tuple[str, str]] = set()
    for place in places:
        if not is_useful_place(place):
            continue
        key = (place.id or "", f"{place.latitude:.5f},{place.longitude:.5f}")
        if key in seen:
            continue
        seen.add(key)
        useful.append(place)
    return useful[:limit]


def get_api_key() -> str:
    api_key = os.getenv("GEOAPIFY_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503, detail="Places service is not configured."
        )
    return api_key


def get_http_client(request: Request) -> httpx.AsyncClient | None:
    # Created at startup (main.lifespan); None only if startup has not run.
    return getattr(request.app.state, "http_client", None)


async def geoapify_get(
    client: httpx.AsyncClient,
    url: str,
    params: dict,
    *,
    provider: str,
    bad_request_detail: str,
) -> dict:
    """GET a Geoapify endpoint and map transport/upstream failures to safe
    HTTP errors. Upstream bodies are never forwarded (they may echo the key)."""
    if client is None:
        raise HTTPException(status_code=503, detail=f"{provider} is not ready.")
    try:
        response = await client.get(url, params=params, timeout=REQUEST_TIMEOUT)
    except httpx.TimeoutException:
        logger.warning("Geoapify request timed out")
        raise HTTPException(status_code=504, detail=f"{provider} timed out.")
    except httpx.RequestError as exc:
        logger.warning("Geoapify request failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail=f"{provider} is unreachable.")

    if response.status_code != 200:
        logger.warning("Geoapify returned HTTP %s", response.status_code)
        if response.status_code == 400:
            raise HTTPException(status_code=400, detail=bad_request_detail)
        if response.status_code == 429:
            raise HTTPException(status_code=503, detail=f"{provider} rate limit reached.")
        raise HTTPException(status_code=502, detail=f"{provider} error.")

    try:
        data = response.json()
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=502, detail=f"Invalid response from {provider.lower()}."
        )
    return data


def parse_categories(raw: str | None) -> str:
    if raw is None or not raw.strip():
        return DEFAULT_CATEGORIES
    categories = list(
        dict.fromkeys(c.strip().lower() for c in raw.split(",") if c.strip())
    )
    if not categories:
        return DEFAULT_CATEGORIES
    if len(categories) > MAX_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"At most {MAX_CATEGORIES} categories are allowed.",
        )
    invalid = [c for c in categories if not CATEGORY_PATTERN.match(c)]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid category value(s): {', '.join(invalid)}",
        )
    return ",".join(categories)


def normalize_feature(feature: dict) -> Place | None:
    props = feature.get("properties") or {}
    coords = (feature.get("geometry") or {}).get("coordinates") or []

    lat = props.get("lat")
    lon = props.get("lon")
    if (lat is None or lon is None) and len(coords) >= 2:
        lon, lat = coords[0], coords[1]
    if lat is None or lon is None:
        return None

    address = props.get("formatted")
    if not address:
        parts = [props.get("address_line1"), props.get("address_line2")]
        address = ", ".join(p for p in parts if p) or None

    categories = props.get("categories")
    return Place(
        id=props.get("place_id"),
        name=props.get("name"),
        address=address,
        latitude=lat,
        longitude=lon,
        categories=categories if isinstance(categories, list) else [],
    )


def name_sort_key(name: str) -> tuple[str, str]:
    """Case- and accent-insensitive key, so "À la mémoire" sorts with "A" and
    "eiffel" with "Eiffel". Ties fall back to the case-folded original."""
    folded = unicodedata.normalize("NFKD", name.strip()).casefold()
    base = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return base, name.strip().casefold()


def sort_places(places: list[Place], sort: str) -> list[Place]:
    if sort == "relevance":
        return places
    named = [p for p in places if p.name and p.name.strip()]
    named.sort(key=lambda p: name_sort_key(p.name), reverse=(sort == "name_desc"))
    return named


async def fetch_places(
    client: httpx.AsyncClient,
    api_key: str,
    *,
    latitude: float,
    longitude: float,
    radius: int,
    categories: str,
    limit: int,
) -> list[Place]:
    """Places around a point, in provider (proximity) order. Shared by
    GET /api/places and the trip planner. Raises HTTPException on failures."""
    params = {
        "categories": categories,
        "filter": f"circle:{longitude},{latitude},{radius}",
        "bias": f"proximity:{longitude},{latitude}",
        "limit": limit,
        "apiKey": api_key,
    }
    data = await geoapify_get(
        client,
        GEOAPIFY_PLACES_URL,
        params,
        provider="Places provider",
        bad_request_detail="Places provider rejected the request; check the categories.",
    )
    features = data.get("features")
    if not isinstance(features, list):
        raise HTTPException(
            status_code=502, detail="Invalid response from places provider."
        )
    return [p for f in features if isinstance(f, dict) and (p := normalize_feature(f))]


@router.get(
    "/places",
    response_model=PlacesResponse,
    responses=errors(400, 502, 503, 504, d400="The places provider rejected the request (for example, an unknown category)."),
)
async def list_places(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    radius: int = Query(5000, ge=1, le=50000, description="Search radius in meters"),
    categories: str | None = Query(
        None,
        max_length=1000,
        description="Comma-separated Geoapify categories, e.g. tourism.sights,catering.restaurant",
    ),
    limit: int = Query(20, ge=1, le=100),
    sort: Literal["relevance", "name", "name_desc"] = "relevance",
    api_key: str = Depends(get_api_key),
    client: httpx.AsyncClient = Depends(get_http_client),
):
    parsed_categories = parse_categories(categories)
    provider_limit = min(max(limit * 2, 20), 100)
    places = await fetch_places(
        client,
        api_key,
        latitude=latitude,
        longitude=longitude,
        radius=radius,
        categories=parsed_categories,
        limit=provider_limit,
    )
    places = filter_places(places, limit)

    # A sparse first pass is common in cities whose OSM attraction coverage is
    # concentrated in a historic core. Broaden only the same attraction
    # categories and keep the geographic center; never substitute businesses.
    if len(places) < min(limit, 3) and radius < 20000:
        broadened = await fetch_places(
            client,
            api_key,
            latitude=latitude,
            longitude=longitude,
            radius=min(radius * 2, 20000),
            categories=parsed_categories,
            limit=provider_limit,
        )
        places = filter_places(places + broadened, limit)

    places = sort_places(places, sort)
    return PlacesResponse(count=len(places), places=places)
