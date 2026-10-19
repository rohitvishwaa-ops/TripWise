import os
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware

from ai_planner import router as planner_router
from api_docs import mark_trip_header_required
from database import init_db
from geocode import router as geocode_router
from itinerary import router as itinerary_router
from places import router as places_router
from trip_edits import router as trip_edits_router
from trips import router as trips_router

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    async with httpx.AsyncClient() as client:
        app.state.http_client = client
        yield


app = FastAPI(
    title="TripWise API",
    version="1.0.0",
    description=(
        "Destination discovery (Geoapify), saved places and day-by-day trip plans for "
        "TripWise. Authenticated endpoints use verified Firebase identities; guest "
        "itinerary and trip endpoints remain scoped to X-Trip-ID."
    ),
    lifespan=lifespan,
)


def custom_openapi():
    """Generated schema plus documentation-only adjustments (see api_docs)."""
    if app.openapi_schema is None:
        app.openapi_schema = mark_trip_header_required(
            get_openapi(
                title=app.title,
                version=app.version,
                description=app.description,
                routes=app.routes,
            )
        )
    return app.openapi_schema


app.openapi = custom_openapi

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(places_router)
app.include_router(geocode_router)
app.include_router(itinerary_router)
app.include_router(trips_router)
app.include_router(trip_edits_router)
app.include_router(planner_router)


@app.get("/health")
def health():
    return {"status": "ok"}
