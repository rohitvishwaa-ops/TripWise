"""SQLAlchemy engine/session setup for the TripWise PostgreSQL (Neon) database."""

import logging
import os
import uuid
from collections.abc import Iterator
from datetime import date, datetime, timezone
from datetime import date as CalendarDate

from fastapi import HTTPException
from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

logger = logging.getLogger(__name__)

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class Base(DeclarativeBase):
    pass


class ItineraryItem(Base):
    __tablename__ = "itinerary_items"
    __table_args__ = (
        UniqueConstraint("trip_id", "place_id", name="uq_itinerary_trip_place"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trip_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    place_id: Mapped[str] = mapped_column(String(512), nullable=False)
    name: Mapped[str | None] = mapped_column(String(500))
    address: Mapped[str | None] = mapped_column(String(1000))
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    categories: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- Trip planner -----------------------------------------------------------
# A trip belongs to one anonymous browser (owner_id = X-Trip-ID). Children are
# removed by ON DELETE CASCADE in the database and by the ORM cascade.

PACES = ("relaxed", "balanced", "packed")
PLANNERS = ("auto", "ai")
ACTIVITY_KINDS = ("place", "transfer")
ACTIVITY_SLOTS = ("morning", "afternoon", "evening")
ACTIVITY_SOURCES = ("auto", "ai", "user")
MAX_TRIP_DAYS = 30


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Trip(Base):
    __tablename__ = "trips"
    __table_args__ = (
        CheckConstraint(_in("pace", PACES), name="ck_trips_pace"),
        CheckConstraint(_in("planner", PLANNERS), name="ck_trips_planner"),
        CheckConstraint(f"num_days BETWEEN 1 AND {MAX_TRIP_DAYS}", name="ck_trips_num_days"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    num_days: Mapped[int] = mapped_column(Integer, nullable=False)
    pace: Mapped[str] = mapped_column(String(16), nullable=False, default="balanced")
    interests: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    planner: Mapped[str] = mapped_column(String(8), nullable=False, default="auto")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    cities: Mapped[list["TripCity"]] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TripCity.position",
    )
    days: Mapped[list["TripDay"]] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TripDay.day_index",
    )


class TripCity(Base):
    __tablename__ = "trip_cities"
    __table_args__ = (
        UniqueConstraint("trip_id", "position", name="uq_trip_cities_position"),
        CheckConstraint(f"days BETWEEN 1 AND {MAX_TRIP_DAYS}", name="ck_trip_cities_days"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trip_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="CASCADE"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(String(1000))
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    days: Mapped[int] = mapped_column(Integer, nullable=False)

    trip: Mapped[Trip] = relationship(back_populates="cities")


class TripDay(Base):
    __tablename__ = "trip_days"
    __table_args__ = (
        UniqueConstraint("trip_id", "day_index", name="uq_trip_days_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trip_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="CASCADE"), index=True, nullable=False
    )
    city_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trip_cities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    day_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # The attribute is named `date`, which shadows the `date` type inside this
    # class body, so use the alias and state nullability explicitly.
    date: Mapped[CalendarDate | None] = mapped_column(Date, nullable=True)
    theme: Mapped[str | None] = mapped_column(String(200))
    generated_by: Mapped[str | None] = mapped_column(String(8))

    trip: Mapped[Trip] = relationship(back_populates="days")
    city: Mapped[TripCity] = relationship()
    activities: Mapped[list["TripActivity"]] = relationship(
        back_populates="day",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TripActivity.position",
    )


class TripActivity(Base):
    __tablename__ = "trip_activities"
    __table_args__ = (
        CheckConstraint(_in("kind", ACTIVITY_KINDS), name="ck_trip_activities_kind"),
        CheckConstraint(f"slot IS NULL OR {_in('slot', ACTIVITY_SLOTS)}", name="ck_trip_activities_slot"),
        CheckConstraint(_in("source", ACTIVITY_SOURCES), name="ck_trip_activities_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trip_days.id", ondelete="CASCADE"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="place")
    place_id: Mapped[str | None] = mapped_column(String(512))
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    address: Mapped[str | None] = mapped_column(String(1000))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    categories: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    slot: Mapped[str | None] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(String(1000))
    source: Mapped[str] = mapped_column(String(8), nullable=False, default="user")

    day: Mapped[TripDay] = relationship(back_populates="activities")


def enable_sqlite_foreign_keys(engine: Engine) -> None:
    """SQLite ignores FOREIGN KEY / ON DELETE CASCADE unless enabled per connection."""
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def _fk_pragma(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def build_database_url(raw_url: str) -> URL:
    """Use the psycopg (v3) driver and require SSL for non-local PostgreSQL hosts."""
    url = make_url(raw_url)
    if url.drivername in ("postgres", "postgresql"):
        url = url.set(drivername="postgresql+psycopg")
    if (
        url.drivername.startswith("postgresql")
        and url.host not in LOCAL_HOSTS
        and "sslmode" not in url.query
    ):
        url = url.update_query_dict({"sslmode": "require"})
    return url


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine | None:
    """Create the engine lazily so the app (and tests) run without DATABASE_URL."""
    global _engine, _session_factory
    if _engine is None:
        raw_url = os.getenv("DATABASE_URL", "").strip()
        if not raw_url:
            return None
        _engine = create_engine(
            build_database_url(raw_url),
            pool_pre_ping=True,  # Neon closes idle connections
            pool_recycle=300,
        )
        enable_sqlite_foreign_keys(_engine)
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def init_db() -> None:
    """Create missing tables. Never drops or alters existing tables/data.

    Failures are logged rather than raised so /health and /api/places keep
    working; itinerary requests then return 503 until the database is reachable.
    """
    try:
        engine = get_engine()
        if engine is None:
            logger.warning("DATABASE_URL is not set; itinerary endpoints are disabled.")
            return
        Base.metadata.create_all(engine, checkfirst=True)
    except (SQLAlchemyError, ValueError) as exc:
        logger.error("Database initialization failed: %s", type(exc).__name__)


def get_db() -> Iterator[Session]:
    try:
        engine = get_engine()
    except (SQLAlchemyError, ValueError) as exc:
        # Malformed DATABASE_URL; never echo the URL (it contains credentials).
        logger.error("Invalid DATABASE_URL: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503, detail="Itinerary storage is misconfigured."
        )
    if engine is None or _session_factory is None:
        raise HTTPException(
            status_code=503, detail="Itinerary storage is not configured."
        )
    with _session_factory() as session:
        yield session
