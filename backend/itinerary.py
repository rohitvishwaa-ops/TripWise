"""Anonymous, per-trip itinerary stored in PostgreSQL."""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from api_docs import errors
from auth import get_request_owner
from database import ItineraryItem, get_db

logger = logging.getLogger(__name__)

PLACE_ID_PATTERN = r"^[A-Za-z0-9_.:-]+$"

router = APIRouter(prefix="/api/itinerary", tags=["itinerary"])


def canonical_guest_id(x_trip_id: str | None) -> str:
    if not x_trip_id:
        raise HTTPException(status_code=400, detail="Missing X-Trip-ID header.")
    try:
        parsed = uuid.UUID(x_trip_id.strip())
    except ValueError:
        raise HTTPException(
            status_code=400, detail="X-Trip-ID must be a valid UUID."
        )
    if str(parsed) != x_trip_id.strip().lower():
        # Reject braces/urn/hex-only forms; only the canonical 8-4-4-4-12 form.
        raise HTTPException(
            status_code=400, detail="X-Trip-ID must be a valid UUID."
        )
    return str(parsed)


def get_trip_id(x_trip_id: str | None = Header(None, alias="X-Trip-ID")) -> str:
    return canonical_guest_id(x_trip_id)


class ItineraryPlaceIn(BaseModel):
    """Same shape as a place returned by GET /api/places."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: str = Field(..., min_length=1, max_length=512, pattern=PLACE_ID_PATTERN)
    name: str | None = Field(None, max_length=500)
    address: str | None = Field(None, max_length=1000)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    categories: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("categories")
    @classmethod
    def check_categories(cls, value: list[str]) -> list[str]:
        cleaned = [c.strip() for c in value]
        if any(not c or len(c) > 100 for c in cleaned):
            raise ValueError("each category must be 1-100 characters")
        return list(dict.fromkeys(cleaned))


class ItineraryPlaceOut(BaseModel):
    id: str
    name: str | None
    address: str | None
    latitude: float
    longitude: float
    categories: list[str]
    added_at: datetime


class ItineraryResponse(BaseModel):
    trip_id: str
    count: int
    places: list[ItineraryPlaceOut]


def to_out(item: ItineraryItem) -> ItineraryPlaceOut:
    return ItineraryPlaceOut(
        id=item.place_id,
        name=item.name,
        address=item.address,
        latitude=item.latitude,
        longitude=item.longitude,
        categories=item.categories or [],
        added_at=item.created_at,
    )


def database_unavailable(exc: SQLAlchemyError) -> HTTPException:
    logger.error("Database error: %s", type(exc).__name__)
    return HTTPException(status_code=503, detail="Itinerary storage is unavailable.")


def find_item(db: Session, trip_id: str, place_id: str) -> ItineraryItem | None:
    return db.scalars(
        select(ItineraryItem).where(
            ItineraryItem.trip_id == trip_id, ItineraryItem.place_id == place_id
        )
    ).first()


@router.get("", response_model=ItineraryResponse, responses=errors(400, 503))
def list_itinerary(
    trip_id: str = Depends(get_request_owner), db: Session = Depends(get_db)
):
    try:
        items = db.scalars(
            select(ItineraryItem)
            .where(ItineraryItem.trip_id == trip_id)
            .order_by(ItineraryItem.created_at, ItineraryItem.id)
        ).all()
    except SQLAlchemyError as exc:
        raise database_unavailable(exc)
    places = [to_out(i) for i in items]
    return ItineraryResponse(trip_id=trip_id, count=len(places), places=places)


@router.post(
    "",
    response_model=ItineraryPlaceOut,
    status_code=201,
    responses=errors(400, 409, 503, d409="The place is already in this browser's itinerary."),
)
def add_to_itinerary(
    place: ItineraryPlaceIn,
    trip_id: str = Depends(get_request_owner),
    db: Session = Depends(get_db),
):
    try:
        if find_item(db, trip_id, place.id) is not None:
            raise HTTPException(
                status_code=409, detail="Place is already in this itinerary."
            )
        item = ItineraryItem(
            trip_id=trip_id,
            place_id=place.id,
            name=place.name,
            address=place.address,
            latitude=place.latitude,
            longitude=place.longitude,
            categories=place.categories,
        )
        db.add(item)
        db.commit()
    except IntegrityError:
        # Concurrent insert of the same place hit the unique constraint.
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Place is already in this itinerary."
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise database_unavailable(exc)
    return to_out(item)


@router.delete(
    "/{place_id}",
    status_code=204,
    responses=errors(400, 404, 503, d404="The place is not in this browser's itinerary."),
)
def remove_from_itinerary(
    place_id: str = Path(..., min_length=1, max_length=512, pattern=PLACE_ID_PATTERN),
    trip_id: str = Depends(get_request_owner),
    db: Session = Depends(get_db),
):
    try:
        item = find_item(db, trip_id, place_id)
        if item is None:
            raise HTTPException(
                status_code=404, detail="Place not found in this itinerary."
            )
        db.delete(item)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise database_unavailable(exc)
    return Response(status_code=204)
