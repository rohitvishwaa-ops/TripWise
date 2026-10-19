"""Trip planner storage: create, list, read, update and delete trips.

Every trip belongs to one anonymous browser, identified by the same X-Trip-ID
header used by /api/itinerary. A trip owned by another browser is reported as
404 so its existence is not revealed. Generation (auto/AI) comes later; this
module only stores the trip, its cities and one empty day per trip day.
"""

import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from database import (
    MAX_TRIP_DAYS,
    Trip,
    TripActivity,
    TripCity,
    TripDay,
    get_db,
    utcnow,
)
from auth import get_request_owner as get_owner_id
from places import get_api_key, get_http_client
import ai_planner
from api_docs import errors
from planner import (
    InsufficientPlacesError,
    Plan,
    activities_per_day,
    build_plan,
    clean_groups,
    exclude_keys,
    fetch_candidates,
    plan_keys,
    trip_pool,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trips", tags=["trips"])

MAX_CITIES = 10
INTERESTS = ("culture", "history", "nature", "food", "shopping", "nightlife", "beaches", "entertainment")
Interest = Literal[
    "culture", "history", "nature", "food", "shopping", "nightlife", "beaches", "entertainment"
]
Pace = Literal["relaxed", "balanced", "packed"]
TripIdPath = Path(..., description="Trip UUID")


# --- Request models ---------------------------------------------------------


def _clean_title(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("title must not be blank")
    return cleaned


class CityIn(BaseModel):
    """A resolved destination, e.g. one result from GET /api/geocode."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=200)
    address: str | None = Field(None, max_length=1000)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    days: int | None = Field(
        None, ge=1, le=MAX_TRIP_DAYS, description="Days in this city; omit to share num_days evenly."
    )


def allocate_days(explicit: list[int | None], total: int | None) -> list[int]:
    """Days per city. Explicit values are kept; cities without a value share
    what is left of `total` as evenly as possible (earlier cities get the
    extra day), and every city gets at least one day."""
    fixed = sum(d for d in explicit if d is not None)
    missing = [i for i, d in enumerate(explicit) if d is None]
    if not missing:
        if total is not None and total != fixed:
            raise ValueError(f"num_days ({total}) does not match the days given per city ({fixed})")
        return list(explicit)
    if total is None:
        raise ValueError("give days for every city, or num_days for the whole trip")
    remaining = total - fixed
    if remaining < len(missing):
        raise ValueError(f"num_days ({total}) leaves less than one day for some cities")
    base, extra = divmod(remaining, len(missing))
    out = list(explicit)
    for k, i in enumerate(missing):
        out[i] = base + (1 if k < extra else 0)
    return out


def _same_place(a: "CityIn", b: "CityIn") -> bool:
    from planner import distance_km

    return a.name.casefold() == b.name.casefold() or distance_km(
        a.latitude, a.longitude, b.latitude, b.longitude
    ) < 1.0


class TripCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(None, max_length=120)
    start_date: date | None = None
    pace: Pace = "balanced"
    interests: list[Interest] = Field(default_factory=list, max_length=len(INTERESTS))
    cities: list[CityIn] = Field(..., min_length=1, max_length=MAX_CITIES)
    num_days: int | None = Field(
        None, ge=1, le=MAX_TRIP_DAYS, description="Total days; required if a city has no days."
    )
    generate: bool = Field(
        False, description="Fill the days automatically with real places from each city."
    )
    planner: Literal["auto", "ai"] = Field(
        "auto",
        description='"ai" lets the optional AI layer choose among real candidates; '
        "falls back to the automatic planner on any problem.",
    )

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str | None) -> str | None:
        return _clean_title(value)

    @field_validator("interests")
    @classmethod
    def dedupe_interests(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def check_total_days(self):
        allocation = allocate_days([c.days for c in self.cities], self.num_days)
        total = sum(allocation)
        if total > MAX_TRIP_DAYS:
            raise ValueError(f"a trip can last at most {MAX_TRIP_DAYS} days in total")
        if len(self.cities) > 1 and total < 2:
            raise ValueError("a multi-city trip needs at least 2 days")
        for a, b in zip(self.cities, self.cities[1:]):
            if _same_place(a, b):
                raise ValueError(f"{b.name} is listed twice in a row; remove one of them")
        if self.planner == "ai" and not self.generate:
            raise ValueError('planner "ai" only applies when generate is true')
        if self.planner == "ai" and len(self.cities) > 1:
            raise ValueError("AI planning currently supports single-city trips only")
        return self

    def allocation(self) -> list[int]:
        return allocate_days([c.days for c in self.cities], self.num_days)


class TripUpdate(BaseModel):
    """Partial update. Cities and days are changed by later planner endpoints."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(None, max_length=120)
    start_date: date | None = None
    pace: Pace | None = None
    interests: list[Interest] | None = Field(None, max_length=len(INTERESTS))

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str | None) -> str | None:
        return _clean_title(value)

    @field_validator("interests")
    @classmethod
    def dedupe_interests(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else list(dict.fromkeys(value))

    @model_validator(mode="after")
    def check_not_empty(self):
        if not self.model_fields_set:
            raise ValueError("provide at least one field to update")
        for field in ("title", "pace", "interests"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


# --- Response models --------------------------------------------------------


class CityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    name: str
    address: str | None
    latitude: float
    longitude: float
    days: int


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    kind: str
    place_id: str | None
    name: str
    address: str | None
    latitude: float | None
    longitude: float | None
    categories: list[str]
    slot: str | None
    note: str | None
    source: str


class DayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    day_index: int
    date: date | None
    city_id: int
    theme: str | None
    generated_by: str | None
    activities: list[ActivityOut]


class TripSummary(BaseModel):
    id: str
    title: str
    start_date: date | None
    end_date: date | None
    num_days: int
    pace: str
    interests: list[str]
    planner: str
    city_names: list[str]
    created_at: datetime
    updated_at: datetime


class TripOut(TripSummary):
    cities: list[CityOut]
    days: list[DayOut]
    warnings: list[str] = []


class TripListResponse(BaseModel):
    count: int
    trips: list[TripSummary]


# --- Helpers ----------------------------------------------------------------


def end_date(trip: Trip) -> date | None:
    return trip.start_date + timedelta(days=trip.num_days - 1) if trip.start_date else None


def summary_fields(trip: Trip) -> dict:
    return {
        "id": trip.id,
        "title": trip.title,
        "start_date": trip.start_date,
        "end_date": end_date(trip),
        "num_days": trip.num_days,
        "pace": trip.pace,
        "interests": trip.interests or [],
        "planner": trip.planner,
        "city_names": [c.name for c in trip.cities],
        "created_at": trip.created_at,
        "updated_at": trip.updated_at,
    }


def to_out(trip: Trip) -> TripOut:
    return TripOut(
        **summary_fields(trip),
        cities=[CityOut.model_validate(c) for c in trip.cities],
        days=[DayOut.model_validate(d) for d in trip.days],
    )


def assign_dates(trip: Trip) -> None:
    for day in trip.days:
        day.date = trip.start_date + timedelta(days=day.day_index) if trip.start_date else None


def storage_unavailable(exc: SQLAlchemyError) -> HTTPException:
    logger.error("Database error: %s", type(exc).__name__)
    return HTTPException(status_code=503, detail="Trip storage is unavailable.")


def load_trip(db: Session, owner_id: str, trip_id: uuid.UUID) -> Trip:
    trip = db.scalars(
        select(Trip)
        .where(Trip.id == str(trip_id), Trip.owner_id == owner_id)
        .options(
            selectinload(Trip.cities),
            selectinload(Trip.days).selectinload(TripDay.activities),
        )
    ).first()
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found.")
    return trip


# --- Endpoints --------------------------------------------------------------


def save_new_trip(db: Session, owner_id: str, body: TripCreate, plan: Plan | None) -> str:
    """Write the trip, its cities, days and (if planned) activities in ONE
    transaction: either all rows are stored or none are."""
    allocation = body.allocation()
    num_days = sum(allocation)
    names = [c.name for c in body.cities]
    title = body.title or f"Trip to {', '.join(names[:3])}{' and more' if len(names) > 3 else ''}"
    now = utcnow()
    try:
        trip = Trip(
            owner_id=owner_id,
            title=title[:120],
            start_date=body.start_date,
            num_days=num_days,
            pace=body.pace,
            interests=body.interests,
            planner=plan.source if plan is not None else "auto",
            created_at=now,
            updated_at=now,
        )
        # One day per trip day, in city order; filled from the plan if given.
        day_index = 0
        for position, (city_in, city_days) in enumerate(zip(body.cities, allocation)):
            city = TripCity(position=position, **{**city_in.model_dump(), "days": city_days})
            trip.cities.append(city)
            for n in range(city_days):
                day = TripDay(day_index=day_index, city=city)
                if plan is not None:
                    planned = plan.days[day_index]
                    day.theme = planned.theme
                    day.generated_by = plan.source
                    for order, item in enumerate(planned.activities):
                        place = item.candidate.place
                        day.activities.append(
                            TripActivity(
                                position=order,
                                kind="place",
                                place_id=place.id,
                                name=place.name,
                                address=place.address,
                                latitude=place.latitude,
                                longitude=place.longitude,
                                categories=place.categories,
                                slot=item.slot,
                                source=plan.source,
                            )
                        )
                # Generated multi-city trips: a labelled travel step ends each
                # city section. No transport mode, times, costs or durations.
                is_last_day_here = n == city_days - 1
                if plan is not None and is_last_day_here and position + 1 < len(body.cities):
                    nxt = body.cities[position + 1]
                    day.activities.append(
                        TripActivity(
                            position=len(day.activities),
                            kind="transfer",
                            name=f"Travel to {nxt.name}"[:500],
                            address=nxt.address or nxt.name,
                            categories=[],
                            slot=None,
                            source=plan.source,
                        )
                    )
                trip.days.append(day)
                day_index += 1
        assign_dates(trip)
        db.add(trip)
        db.commit()
        return trip.id
    except SQLAlchemyError as exc:
        db.rollback()
        raise storage_unavailable(exc)


async def plan_cities(client: httpx.AsyncClient | None, body: TripCreate) -> Plan:
    """Fetch real places and plan every city BEFORE anything is written, so an
    upstream failure in any city can never leave a half-generated trip."""
    api_key = get_api_key()  # 503 if Geoapify is not configured
    allocation = body.allocation()
    per_day = activities_per_day(body.pace)
    multi = len(body.cities) > 1
    used: set = set()  # places already planned in earlier cities
    days, warnings, source = [], [], "auto"

    for city, city_days in zip(body.cities, allocation):
        center = (city.latitude, city.longitude)
        needed = city_days * per_day
        where = f" for {city.name}" if multi else ""
        try:
            groups = await fetch_candidates(client, api_key, center, body.interests, needed)
        except HTTPException as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=f"Could not generate the itinerary{where}. {exc.detail}",
            )
        groups = exclude_keys(groups, used)
        try:
            plan = await _plan_city(client, body, city, city_days, center, needed, per_day, groups)
        except InsufficientPlacesError as exc:
            plural = "s" if city_days != 1 else ""
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Not enough places found near {city.name} to plan {city_days} day{plural} "
                    f"(found {exc.found}). Try other interests, fewer days, or a larger city."
                ),
            )
        used |= plan_keys(plan)
        days.extend(plan.days)
        warnings.extend(f"{city.name}: {w}" if multi else w for w in plan.warnings)
        source = plan.source
    return Plan(days=days, warnings=warnings, source=source)


async def _plan_city(client, body, city, city_days, center, needed, per_day, groups) -> Plan:
    if body.planner == "ai":  # single-city only (validated in TripCreate)
        unique, _ = clean_groups(groups)
        if len(unique) < city_days:
            raise InsufficientPlacesError(found=len(unique), needed=city_days)
        ai_plan = await ai_planner.plan_trip(
            client,
            city_name=city.name,
            center=center,
            interests=body.interests,
            num_days=city_days,
            per_day=per_day,
            pool=trip_pool(groups, min(ai_planner.MAX_CANDIDATES, max(needed * 2, needed + 10))),
        )
        if ai_plan is not None:
            return ai_plan
        fallback = build_plan(groups, center, city_days, body.pace)
        fallback.warnings.insert(0, ai_planner.fallback_warning())
        return fallback
    return build_plan(groups, center, city_days, body.pace)


@router.post(
    "",
    response_model=TripOut,
    status_code=201,
    responses=errors(
        400, 502, 503, 504,
        d400="Missing or invalid X-Trip-ID, or the provider rejected a place search during generation.",
    ),
)
async def create_trip(
    body: TripCreate,
    owner_id: str = Depends(get_owner_id),
    db: Session = Depends(get_db),
    client: httpx.AsyncClient | None = Depends(get_http_client),
):
    plan = await plan_cities(client, body) if body.generate else None
    trip_id = await run_in_threadpool(save_new_trip, db, owner_id, body, plan)

    def reload() -> TripOut:
        db.expire_all()
        return to_out(load_trip(db, owner_id, uuid.UUID(trip_id)))

    out = await run_in_threadpool(reload)
    if plan is not None:
        out.warnings = plan.warnings
    return out


@router.get("", response_model=TripListResponse, responses=errors(400, 503))
def list_trips(owner_id: str = Depends(get_owner_id), db: Session = Depends(get_db)):
    try:
        trips = db.scalars(
            select(Trip)
            .where(Trip.owner_id == owner_id)
            .options(selectinload(Trip.cities))
            .order_by(Trip.updated_at.desc(), Trip.created_at.desc())
        ).all()
    except SQLAlchemyError as exc:
        raise storage_unavailable(exc)
    summaries = [TripSummary(**summary_fields(t)) for t in trips]
    return TripListResponse(count=len(summaries), trips=summaries)


@router.get("/{trip_id}", response_model=TripOut, responses=errors(400, 404, 503))
def get_trip(
    trip_id: uuid.UUID = TripIdPath,
    owner_id: str = Depends(get_owner_id),
    db: Session = Depends(get_db),
):
    try:
        return to_out(load_trip(db, owner_id, trip_id))
    except SQLAlchemyError as exc:
        raise storage_unavailable(exc)


@router.patch("/{trip_id}", response_model=TripOut, responses=errors(400, 404, 503))
def update_trip(
    body: TripUpdate,
    trip_id: uuid.UUID = TripIdPath,
    owner_id: str = Depends(get_owner_id),
    db: Session = Depends(get_db),
):
    try:
        trip = load_trip(db, owner_id, trip_id)
        changes = body.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(trip, field, value)
        if "start_date" in changes:
            assign_dates(trip)
        trip.updated_at = utcnow()
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise storage_unavailable(exc)
    db.expire_all()
    return to_out(load_trip(db, owner_id, trip_id))


@router.delete("/{trip_id}", status_code=204, responses=errors(400, 404, 503))
def delete_trip(
    trip_id: uuid.UUID = TripIdPath,
    owner_id: str = Depends(get_owner_id),
    db: Session = Depends(get_db),
):
    try:
        trip = load_trip(db, owner_id, trip_id)
        db.delete(trip)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise storage_unavailable(exc)
    return Response(status_code=204)
