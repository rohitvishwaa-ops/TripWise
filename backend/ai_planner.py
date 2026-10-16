"""Optional AI selection layer (Google Gemini REST API via httpx).

The AI never creates places. It receives a short list of real candidate places
(already fetched from Geoapify and cleaned by the automatic planner) under
opaque aliases ("p1", "p2", ...) and may only:
  * choose which of those places go on which day, and
  * suggest a short theme per day.
The server validates every answer (known aliases only, no repeats, exact day
count, stops-per-day limits) and still orders each day nearest-first and
assigns Morning/Afternoon/Evening itself. Any problem (no key, timeout, rate
limit, error status, malformed or invalid output) returns None, and callers
fall back to the deterministic automatic planner with a warning.

Only minimal, non-personal data is sent: city name, interests, pace limits and
for each candidate an alias, name, broad category, interest and rounded
coordinates. Never trip titles, notes, browser IDs or credentials.
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from planner import (
    INTEREST_LABELS,
    Candidate,
    Plan,
    PlannedActivity,
    PlannedDay,
    day_theme,
    order_nearest_neighbour,
    slot_labels,
)

logger = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-3.5-flash-lite"
MODEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.\-]{0,63}$")
TIMEOUT = httpx.Timeout(8.0)
MAX_OUTPUT_TOKENS = 1024
MAX_CANDIDATES = 40
RATE_LIMIT_COOLDOWN_S = 60.0
MAX_THEME_CHARS = 60
# Themes must describe kinds of places, not schedules, prices or distances.
FORBIDDEN_THEME = re.compile(
    r"\d|[$€£¥₹]|\b(am|pm|a\.m|p\.m|o'?clock|hours?|hrs?|minutes?|mins?|open(s|ing)?|clos(e|es|ed|ing)|"
    r"price[sd]?|cost|cheap|expensive|free|tickets?|fee|walk(ing)?|drive|driving|km|kilomet(er|re)s?|miles?)\b",
    re.IGNORECASE,
)

NOT_CONFIGURED_WARNING = (
    "AI planning isn't set up on this server, so this plan was built automatically."
)
FALLBACK_WARNING = "AI selection was unavailable, so this plan was built automatically."

_cooldown_until = 0.0  # monotonic time until which AI calls are skipped after a 429


@dataclass(frozen=True)
class GeminiConfig:
    api_key: str
    model: str


def get_config() -> GeminiConfig | None:
    """Read configuration on every call (never cached, never logged)."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_MODEL
    if not key or not MODEL_PATTERN.match(model):
        return None
    return GeminiConfig(api_key=key, model=model)


class AIUnavailable(Exception):
    """Internal: why the AI result could not be used (never shown verbatim)."""


# --- Prompt -----------------------------------------------------------------

SYSTEM_PROMPT = (
    "You arrange real places into a day-by-day city itinerary. "
    "Use ONLY the place ids given in the input; never invent places or ids. "
    "Return JSON with exactly the requested number of entries in `days`. "
    "Each day lists 1 to max_stops_per_day place ids; put places that are close "
    "together on the same day, balance the traveller's interests, and never use "
    "an id twice in the whole answer. Each day may have a short `theme` of at "
    "most 6 words naming the kinds of places that day (for example "
    "'Museums and gardens'). Do not mention times, opening hours, prices, "
    "tickets, travel times or distances anywhere."
)


def _broad_category(place) -> str | None:
    cats = place.categories or []
    specific = [c for c in cats if not any(o != c and o.startswith(f"{c}.") for o in cats)]
    return (specific or cats or [None])[0]


def build_request(city_name: str, interests: list[str], num_days: int, per_day: int,
                  pool: list[Candidate]) -> tuple[dict, dict[str, Candidate]]:
    aliases = {f"p{i + 1}": c for i, c in enumerate(pool)}
    payload = {
        "city": city_name,
        "days": num_days,
        "max_stops_per_day": per_day,
        "interests": [INTEREST_LABELS.get(i, i) for i in interests],
        "places": [
            {
                "id": alias,
                "name": (c.place.name or "")[:80],
                "category": _broad_category(c.place),
                "interest": INTEREST_LABELS.get(c.interest, c.interest),
                "lat": round(c.lat, 3),
                "lon": round(c.lon, 3),
            }
            for alias, c in aliases.items()
        ],
    }
    schema = {
        "type": "OBJECT",
        "properties": {
            "days": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "place_ids": {"type": "ARRAY", "items": {"type": "STRING", "enum": list(aliases)}},
                        "theme": {"type": "STRING"},
                    },
                    "required": ["place_ids"],
                },
            }
        },
        "required": ["days"],
    }
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "maxOutputTokens": MAX_OUTPUT_TOKENS,
            "temperature": 0.2,
        },
    }
    return body, aliases


# --- Calling and validating -----------------------------------------------------


async def _call(client: httpx.AsyncClient | None, config: GeminiConfig, body: dict) -> dict:
    global _cooldown_until
    if client is None:
        raise AIUnavailable("http client not ready")
    url = f"{GEMINI_BASE_URL}/{config.model}:generateContent"
    try:
        # Key in a header (not the URL), so it can't leak via URLs or exceptions.
        response = await client.post(
            url, json=body, headers={"x-goog-api-key": config.api_key}, timeout=TIMEOUT
        )
    except httpx.TimeoutException:
        raise AIUnavailable("timeout")
    except httpx.RequestError as exc:
        raise AIUnavailable(f"request error {type(exc).__name__}")
    if response.status_code == 429:
        _cooldown_until = time.monotonic() + RATE_LIMIT_COOLDOWN_S
        raise AIUnavailable("rate limited")
    if response.status_code != 200:
        raise AIUnavailable(f"http {response.status_code}")
    try:
        envelope = response.json()
    except ValueError:
        raise AIUnavailable("envelope not json")
    if not isinstance(envelope, dict):
        raise AIUnavailable("envelope not object")
    if (envelope.get("promptFeedback") or {}).get("blockReason"):
        raise AIUnavailable("prompt blocked")
    candidates = envelope.get("candidates")
    if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
        raise AIUnavailable("no candidates")
    first = candidates[0]
    if first.get("finishReason") not in (None, "STOP"):
        raise AIUnavailable(f"finish {first.get('finishReason')}")
    parts = (first.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    try:
        result = json.loads(text)
    except ValueError:
        raise AIUnavailable("answer not json")
    if not isinstance(result, dict):
        raise AIUnavailable("answer not object")
    return result


def clean_theme(value) -> str | None:
    if not isinstance(value, str):
        return None
    theme = " ".join(value.split())
    if not theme or len(theme) > MAX_THEME_CHARS or len(theme.split()) > 8 or FORBIDDEN_THEME.search(theme):
        return None
    return theme


def validate(result: dict, aliases: dict[str, Candidate], num_days: int, per_day: int
             ) -> list[tuple[list[Candidate], str | None]]:
    days = result.get("days")
    if not isinstance(days, list) or len(days) != num_days:
        raise AIUnavailable("wrong day count")
    seen: set[str] = set()
    out = []
    for day in days:
        if not isinstance(day, dict):
            raise AIUnavailable("day not object")
        ids = day.get("place_ids")
        if not isinstance(ids, list) or not 1 <= len(ids) <= per_day:
            raise AIUnavailable("wrong stop count")
        chosen = []
        for alias in ids:
            if not isinstance(alias, str) or alias not in aliases:
                raise AIUnavailable("unknown id")
            if alias in seen:
                raise AIUnavailable("duplicate id")
            seen.add(alias)
            chosen.append(aliases[alias])
        out.append((chosen, clean_theme(day.get("theme"))))
    return out


async def _select(client, city_name, interests, num_days, per_day, pool) -> list[tuple[list[Candidate], str | None]]:
    config = get_config()
    if config is None:
        raise AIUnavailable("not configured")
    if time.monotonic() < _cooldown_until:
        raise AIUnavailable("rate limit cooldown")
    if not pool:
        raise AIUnavailable("no candidates")
    body, aliases = build_request(city_name, interests, num_days, per_day, pool[:MAX_CANDIDATES])
    return validate(await _call(client, config, body), aliases, num_days, per_day)


def _to_day(chosen: list[Candidate], theme: str | None, start: tuple[float, float],
            interest_order: list[str] | None) -> PlannedDay:
    ordered = order_nearest_neighbour(chosen, start)  # server decides the order
    return PlannedDay(
        theme=theme or day_theme(ordered, interest_order),
        activities=[PlannedActivity(c, s) for c, s in zip(ordered, slot_labels(len(ordered)))],
    )


def _short_warning(selected: int, wanted: int, per_day: int) -> list[str]:
    if selected >= wanted:
        return []
    return [f"The AI chose {selected} places, so some days have fewer than {per_day} activities."]


async def plan_trip(client, *, city_name: str, center: tuple[float, float], interests: list[str],
                    num_days: int, per_day: int, pool: list[Candidate]) -> Plan | None:
    """AI-selected multi-day plan, or None (callers fall back automatically)."""
    try:
        days = await _select(client, city_name, interests, num_days, per_day, pool)
    except AIUnavailable as exc:
        logger.warning("AI planner not used: %s", exc)
        return None
    order = interests or None
    plan_days = [_to_day(chosen, theme, center, order) for chosen, theme in days]
    total = sum(len(c) for c, _ in days)
    return Plan(days=plan_days, warnings=_short_warning(total, num_days * per_day, per_day), source="ai")


async def plan_day(client, *, city_name: str, anchor: tuple[float, float], interests: list[str],
                   per_day: int, pool: list[Candidate]) -> tuple[PlannedDay, list[str]] | None:
    """AI-selected single day (for regeneration), or None."""
    try:
        [(chosen, theme)] = await _select(client, city_name, interests, 1, per_day, pool)
    except AIUnavailable as exc:
        logger.warning("AI planner not used: %s", exc)
        return None
    return _to_day(chosen, theme, anchor, interests or None), _short_warning(len(chosen), per_day, per_day)


def fallback_warning() -> str:
    return NOT_CONFIGURED_WARNING if get_config() is None else FALLBACK_WARNING


# --- Status ------------------------------------------------------------------------

router = APIRouter(prefix="/api/planner", tags=["planner"])


class PlannerStatus(BaseModel):
    ai_available: bool
    default_planner: str = "auto"


@router.get("/status", response_model=PlannerStatus)
def planner_status():
    """Whether the optional AI planner is configured. Never returns secrets."""
    return PlannerStatus(ai_available=get_config() is not None)
