"""OpenAPI documentation helpers (documentation only; no runtime behaviour).

Routes declare the error responses they can return with `responses=errors(...)`.
FastAPI adds 422 (request validation) automatically.
"""

from typing import Any

from pydantic import BaseModel

TRIP_ID_HEADER_DESCRIPTION = (
    "Anonymous browser identity: a UUID in canonical 8-4-4-4-12 form, generated "
    "once by the browser (crypto.randomUUID()) and stored in localStorage. "
    "Required; every itinerary and trip operation is scoped to it. Missing or "
    "malformed values return 400."
)


class ErrorResponse(BaseModel):
    detail: str


_DEFAULTS = {
    400: "Missing or invalid X-Trip-ID header (must be a canonical UUID).",
    404: "Not found, or it belongs to another browser (X-Trip-ID).",
    409: "Conflict with the current state (for example, the place is already saved).",
    502: "The places provider (Geoapify) returned an error or could not be reached.",
    503: "Not configured on this server, storage unavailable, or provider rate limit reached.",
    504: "The places provider (Geoapify) timed out.",
}


def errors(*codes: int, **overrides: str) -> dict[int | str, dict[str, Any]]:
    """`responses=` entries for the given status codes.

    Override a description with e.g. `errors(400, 502, d400="...")`.
    """
    out: dict[int | str, dict[str, Any]] = {}
    for code in codes:
        description = overrides.get(f"d{code}", _DEFAULTS[code])
        out[code] = {"model": ErrorResponse, "description": description}
    return out


def mark_trip_header_required(schema: dict) -> dict:
    """The X-Trip-ID dependency is declared optional so that a missing header
    returns a friendly 400 instead of a generic 422. Document it as required."""
    for path in schema.get("paths", {}).values():
        for operation in path.values():
            for param in operation.get("parameters", []):
                if param.get("in") == "header" and param.get("name") == "X-Trip-ID":
                    param["required"] = True
                    param["description"] = TRIP_ID_HEADER_DESCRIPTION
                    param["schema"] = {"type": "string", "format": "uuid"}
    return schema
