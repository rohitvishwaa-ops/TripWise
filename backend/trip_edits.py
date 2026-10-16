"""Editing a saved itinerary: reorder, move, remove, note, add, regenerate a day.

Every endpoint is scoped to the browser's X-Trip-ID: the trip must belong to
it, and any day or activity referenced (in the path or body) must belong to
that trip. Each request is one database transaction; every change returns
the full, updated trip. After any change, a day's activities are renumbered
0..n-1 and their Morning/Afternoon/Evening labels follow that order.
"""

import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.concurrency import run_in_threadpool
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import Trip, TripActivity, TripDay, get_db, utcnow
from itinerary import ItineraryPlaceIn
from itinerary import get_trip_id as get_owner_id
from places import get_api_key, get_http_client
import ai_planner
from api_docs import errors
from planner import (
    Candidate,
    InsufficientPlacesError,
    activities_per_day,
    build_day,
    day_pool,
    distance_km,
    fetch_candidates,
    place_keys,
    slot_labels,
)
from trips import TripOut, load_trip, storage_unavailable, to_out

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trips", tags=["trip editing"])

MAX_NOTE = 500
TripIdPath = Path(..., description="Trip UUID")
DayIdPath = Path(..., ge=1, description="Day id within the trip")
ActivityIdPath = Path(..., ge=1, description="Activity id within the trip")


# --- Request models ---------------------------------------------------------


def _clean_note(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None  # blank note = remove note


class ReorderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity_ids: list[int] = Field(..., max_length=100)

    @field_validator("activity_ids")
    @classmethod
    def no_duplicates(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("activity_ids must not contain duplicates")
        return value


class ActivityUpdate(BaseModel):
    """Change the note and/or move the activity to another day of the trip."""

    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(None, max_length=MAX_NOTE)
    day_id: int | None = Field(None, ge=1)
    position: int | None = Field(None, ge=0, description="Index in the target day; default: end")

    @field_validator("note")
    @classmethod
    def clean_note(cls, value: str | None) -> str | None:
        return _clean_note(value)

    @model_validator(mode="after")
    def not_empty(self):
        if not self.model_fields_set:
            raise ValueError("provide note, day_id and/or position")
        if "day_id" in self.model_fields_set and self.day_id is None:
            raise ValueError("day_id cannot be null")
        return self


class RegenerateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planner: Literal["auto", "ai"] = "auto"


class AddActivityBody(BaseModel):
    """Add a saved place (same shape as My Trip / GET /api/places)."""

    model_config = ConfigDict(extra="forbid")

    place: ItineraryPlaceIn
    day_id: int | None = Field(None, ge=1, description="Default: the day whose stops are closest")
    note: str | None = Field(None, max_length=MAX_NOTE)

    @field_validator("note")
    @classmethod
    def clean_note(cls, value: str | None) -> str | None:
        return _clean_note(value)


# --- Helpers ----------------------------------------------------------------


def find_day(trip: Trip, day_id: int, *, in_body: bool = False) -> TripDay:
    day = next((d for d in trip.days if d.id == day_id), None)
    if day is None:
        if in_body:
            raise HTTPException(status_code=422, detail="day_id is not a day of this trip.")
        raise HTTPException(status_code=404, detail="Day not found in this trip.")
    return day


def find_activity(trip: Trip, activity_id: int) -> tuple[TripDay, TripActivity]:
    for day in trip.days:
        for activity in day.activities:
            if activity.id == activity_id:
                return day, activity
    raise HTTPException(status_code=404, detail="Activity not found in this trip.")


def relabel(activities: list[TripActivity]) -> None:
    """Positions 0..n-1 in list order. Morning/Afternoon/Evening follow the
    order of the real places only; travel steps have no slot."""
    slots = iter(slot_labels(sum(1 for a in activities if a.kind == "place")))
    for position, activity in enumerate(activities):
        activity.position = position
        activity.slot = next(slots) if activity.kind == "place" else None


def insert_index(activities: list[TripActivity]) -> int:
    """Default place for a new or moved stop: before a trailing travel step."""
    index = len(activities)
    while index > 0 and activities[index - 1].kind == "transfer":
        index -= 1
    return index


def ordered(day: TripDay) -> list[TripActivity]:
    return sorted(day.activities, key=lambda a: (a.position, a.id))


def trip_place_keys(trip: Trip, skip_day: TripDay | None = None) -> set:
    keys: set = set()
    for day in trip.days:
        if day is skip_day:
            continue
        for a in day.activities:
            keys |= place_keys(a.place_id, a.name, a.latitude, a.longitude)
    return keys


def commit(db: Session, trip: Trip, owner_id: str) -> TripOut:
    trip.updated_at = utcnow()
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise storage_unavailable(exc)
    db.expire_all()
    return to_out(load_trip(db, owner_id, uuid.UUID(trip.id)))


def loaded(db: Session, owner_id: str, trip_id: uuid.UUID) -> Trip:
    try:
        return load_trip(db, owner_id, trip_id)
    except SQLAlchemyError as exc:
        raise storage_unavailable(exc)


def day_anchor(day: TripDay) -> tuple[float, float] | None:
    points = [(a.latitude, a.longitude) for a in day.activities if a.latitude is not None and a.longitude is not None]
    if not points:
        return None
    return (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))


# --- Endpoints --------------------------------------------------------------


@router.put(
    "/{trip_id}/days/{day_id}/order",
    response_model=TripOut,
    responses=errors(400, 404, 503, d404="Trip not found for this browser, or the day is not part of it."),
)
def reorder_day(
    body: ReorderBody,
    trip_id: uuid.UUID = TripIdPath,
    day_id: int = DayIdPath,
    owner_id: str = Depends(get_owner_id),
    db: Session = Depends(get_db),
):
    """Set the order of a day's activities. Must list each one exactly once."""
    trip = loaded(db, owner_id, trip_id)
    day = find_day(trip, day_id)
    current = {a.id: a for a in day.activities}
    if set(body.activity_ids) != set(current):
        raise HTTPException(
            status_code=422,
            detail="activity_ids must list every activity of this day exactly once.",
        )
    relabel([current[i] for i in body.activity_ids])
    return commit(db, trip, owner_id)


@router.patch(
    "/{trip_id}/activities/{activity_id}",
    response_model=TripOut,
    responses=errors(400, 404, 503, d404="Trip not found for this browser, or the activity is not part of it."),
)
def update_activity(
    body: ActivityUpdate,
    trip_id: uuid.UUID = TripIdPath,
    activity_id: int = ActivityIdPath,
    owner_id: str = Depends(get_owner_id),
    db: Session = Depends(get_db),
):
    """Edit the note, and/or move the activity (to another day or position)."""
    trip = loaded(db, owner_id, trip_id)
    source, activity = find_activity(trip, activity_id)

    if "note" in body.model_fields_set:
        activity.note = body.note

    if "day_id" in body.model_fields_set or "position" in body.model_fields_set:
        target = find_day(trip, body.day_id, in_body=True) if body.day_id is not None else source
        if activity.kind == "transfer" and target is not source:
            raise HTTPException(
                status_code=422,
                detail="Travel steps can't be moved to another day. Remove it instead.",
            )
        source_list = [a for a in ordered(source) if a is not activity]
        target_list = source_list if target is source else ordered(target)
        position = insert_index(target_list) if body.position is None else body.position
        if position > len(target_list):
            raise HTTPException(
                status_code=422,
                detail=f"position must be between 0 and {len(target_list)}.",
            )
        target_list.insert(position, activity)
        if target is not source:
            activity.day = target  # FK update inside this transaction
            relabel(source_list)
        relabel(target_list)

    return commit(db, trip, owner_id)


@router.delete(
    "/{trip_id}/activities/{activity_id}",
    response_model=TripOut,
    responses=errors(400, 404, 503, d404="Trip not found for this browser, or the activity is not part of it."),
)
def delete_activity(
    trip_id: uuid.UUID = TripIdPath,
    activity_id: int = ActivityIdPath,
    owner_id: str = Depends(get_owner_id),
    db: Session = Depends(get_db),
):
    trip = loaded(db, owner_id, trip_id)
    day, activity = find_activity(trip, activity_id)
    remaining = [a for a in ordered(day) if a is not activity]
    day.activities.remove(activity)  # delete-orphan cascade
    relabel(remaining)
    return commit(db, trip, owner_id)


@router.post(
    "/{trip_id}/activities",
    response_model=TripOut,
    status_code=201,
    responses=errors(400, 404, 409, 503, d409="This place is already in the trip."),
)
def add_activity(
    body: AddActivityBody,
    trip_id: uuid.UUID = TripIdPath,
    owner_id: str = Depends(get_owner_id),
    db: Session = Depends(get_db),
):
    """Add a saved place to a day (given, or the day whose stops are closest)."""
    trip = loaded(db, owner_id, trip_id)
    place = body.place
    if place_keys(place.id, place.name, place.latitude, place.longitude) & trip_place_keys(trip):
        raise HTTPException(status_code=409, detail="This place is already in the trip.")

    if body.day_id is not None:
        day = find_day(trip, body.day_id, in_body=True)
    else:
        def score(d: TripDay):
            anchor = day_anchor(d)
            dist = distance_km(place.latitude, place.longitude, *anchor) if anchor else float("inf")
            return (dist, len(d.activities), d.day_index)

        day = min(trip.days, key=score)

    existing = ordered(day)
    activity = TripActivity(
        kind="place",
        place_id=place.id,
        name=(place.name or "Unnamed place")[:500],
        address=place.address,
        latitude=place.latitude,
        longitude=place.longitude,
        categories=place.categories,
        note=body.note,
        source="user",
        position=len(day.activities),
    )
    day.activities.append(activity)
    existing.insert(insert_index(existing), activity)
    relabel(existing)
    return commit(db, trip, owner_id)


@router.post(
    "/{trip_id}/days/{day_id}/regenerate",
    response_model=TripOut,
    responses=errors(
        400, 404, 409, 502, 503, 504,
        d404="Trip not found for this browser, or the day is not part of it.",
        d409="The trip changed while regenerating; try again.",
    ),
)
async def regenerate_day(
    body: RegenerateBody | None = None,
    trip_id: uuid.UUID = TripIdPath,
    day_id: int = DayIdPath,
    owner_id: str = Depends(get_owner_id),
    db: Session = Depends(get_db),
    client: httpx.AsyncClient | None = Depends(get_http_client),
):
    """Replace one day's activities with fresh automatic suggestions.

    Places already scheduled on other days are never used; other days are not
    touched. Places are fetched BEFORE any change, and the replacement is one
    transaction, so a failure leaves the day exactly as it was.
    """

    def read():
        trip = loaded(db, owner_id, trip_id)
        day = find_day(trip, day_id)
        city = next(c for c in trip.cities if c.id == day.city_id)
        return {
            "center": (city.latitude, city.longitude),
            "anchor": day_anchor(day) or (city.latitude, city.longitude),
            "interests": list(trip.interests or []),
            "pace": trip.pace,
            "exclude": trip_place_keys(trip, skip_day=day),
            "avoid": trip_place_keys(trip) - trip_place_keys(trip, skip_day=day),
            "city_name": city.name,
            "multi_city": len(trip.cities) > 1,
            "planned_elsewhere": sum(len(d.activities) for d in trip.days if d.id != day.id),
        }

    info = await run_in_threadpool(read)
    if body is not None and body.planner == "ai" and info["multi_city"]:
        raise HTTPException(
            status_code=422, detail="AI planning currently supports single-city trips only."
        )
    api_key = get_api_key()
    per_day = activities_per_day(info["pace"])
    needed = per_day + info["planned_elsewhere"] + per_day  # room for exclusions
    try:
        groups: list[list[Candidate]] = await fetch_candidates(
            client, api_key, info["center"], info["interests"], needed
        )
    except HTTPException as exc:
        raise HTTPException(status_code=exc.status_code, detail=f"Could not regenerate the day. {exc.detail}")

    use_ai = body is not None and body.planner == "ai"
    source = "auto"
    try:
        ai_result = None
        if use_ai:
            pool = day_pool(groups, info["anchor"], info["exclude"], info["avoid"], ai_planner.MAX_CANDIDATES)
            if not pool:
                raise InsufficientPlacesError(found=0, needed=1)
            ai_result = await ai_planner.plan_day(
                client,
                city_name=info["city_name"],
                anchor=info["anchor"],
                interests=info["interests"],
                per_day=per_day,
                pool=pool,
            )
        if ai_result is not None:
            planned, warnings = ai_result
            source = "ai"
        else:
            planned, warnings = build_day(
                groups,
                info["anchor"],
                info["pace"],
                exclude=info["exclude"],
                avoid=info["avoid"],
                interest_order=info["interests"] or None,
            )
            if use_ai:
                warnings = [ai_planner.fallback_warning(), *warnings]
    except InsufficientPlacesError:
        raise HTTPException(
            status_code=422,
            detail=(
                f"No other places were found near {info['city_name']} for this day. "
                "Try different interests, or edit the day by hand."
            ),
        )

    def write() -> TripOut:
        trip = loaded(db, owner_id, trip_id)
        day = find_day(trip, day_id)
        # Re-check against other days in case the trip changed meanwhile.
        taken = trip_place_keys(trip, skip_day=day)
        items = [
            item for item in planned.activities
            if not (place_keys(item.candidate.place.id, item.candidate.place.name,
                               item.candidate.lat, item.candidate.lon) & taken)
        ]
        if not items:
            raise HTTPException(status_code=409, detail="The trip changed while regenerating. Try again.")
        # Replace the day's places; keep its travel step(s), at the end.
        transfers = [a for a in ordered(day) if a.kind == "transfer"]
        for old in [a for a in day.activities if a.kind != "transfer"]:
            day.activities.remove(old)
        db.flush()  # delete old rows before inserting replacements (same transaction)
        new_places = []
        for item in items:
            p = item.candidate.place
            activity = TripActivity(
                kind="place", place_id=p.id, name=p.name, address=p.address,
                latitude=p.latitude, longitude=p.longitude, categories=p.categories,
                source=source, position=0,
            )
            day.activities.append(activity)
            new_places.append(activity)
        relabel(new_places + transfers)
        day.theme = planned.theme
        day.generated_by = source
        return commit(db, trip, owner_id)

    try:
        out = await run_in_threadpool(write)
    except SQLAlchemyError as exc:
        db.rollback()
        raise storage_unavailable(exc)
    out.warnings = warnings
    return out
