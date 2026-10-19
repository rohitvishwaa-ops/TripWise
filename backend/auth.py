"""Firebase ID-token verification and authenticated workspace identity.

The browser's X-Trip-ID remains a legacy guest identifier. It is never used
when an Authorization bearer token is present. Authenticated ownership is a
stable UUID derived on the server from the verified Firebase UID.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass

from fastapi import Header, HTTPException
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials, get_app, initialize_app
from firebase_admin.exceptions import FirebaseError

FIREBASE_NAMESPACE = uuid.UUID("6d5f4a7d-1d35-4a7a-9bb4-cb1d7d884f0a")


@dataclass(frozen=True)
class AuthIdentity:
    uid: str
    owner_id: str
    email: str | None = None


def _project_id() -> str:
    project_id = os.getenv("FIREBASE_PROJECT_ID", "").strip()
    if not project_id:
        raise HTTPException(status_code=503, detail="Authentication is not configured.")
    return project_id


def _firebase_app():
    project_id = _project_id()
    try:
        return get_app()
    except ValueError:
        raw_credentials = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
        if raw_credentials:
            try:
                service_account = json.loads(raw_credentials)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=503, detail="Authentication is misconfigured.") from exc
            return initialize_app(credentials.Certificate(service_account), {"projectId": project_id})
        # Application Default Credentials are used on Render when configured
        # without placing a service-account file in the repository.
        return initialize_app(options={"projectId": project_id})


def owner_id_for_uid(uid: str) -> str:
    """Map a verified Firebase UID to a stable, non-client-controlled UUID."""
    digest = hashlib.sha256(uid.encode("utf-8")).hexdigest()
    return str(uuid.uuid5(FIREBASE_NAMESPACE, digest))


def verify_firebase_token(token: str) -> AuthIdentity:
    project_id = _project_id()
    try:
        decoded = firebase_auth.verify_id_token(token, app=_firebase_app())
    except (FirebaseError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid authentication token.") from exc

    uid = decoded.get("uid") or decoded.get("sub")
    issuer = decoded.get("iss")
    audience = decoded.get("aud")
    if (
        not isinstance(uid, str)
        or not uid
        or issuer != f"https://securetoken.google.com/{project_id}"
        or audience != project_id
    ):
        raise HTTPException(status_code=401, detail="Invalid authentication token.")
    if decoded.get("email_verified") is not True:
        raise HTTPException(status_code=403, detail="Verify your email before using an account.")

    return AuthIdentity(uid=uid, owner_id=owner_id_for_uid(uid), email=decoded.get("email"))


def get_request_owner(
    authorization: str | None = Header(None, include_in_schema=False),
    x_trip_id: str | None = Header(None, alias="X-Trip-ID"),
) -> str:
    """Return authenticated ownership, or preserve the legacy guest path.

    A malformed or expired bearer token is an authentication failure. It must
    not silently downgrade to the weaker guest identity.
    """
    if authorization is not None:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise HTTPException(status_code=401, detail="Invalid authentication token.")
        return verify_firebase_token(token.strip()).owner_id

    # Import locally to avoid a dependency cycle: itinerary owns the legacy
    # canonical UUID validation used by all existing guest endpoints.
    from itinerary import canonical_guest_id

    return canonical_guest_id(x_trip_id)
