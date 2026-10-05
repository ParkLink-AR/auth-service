from __future__ import annotations

from uuid import UUID

import httpx
from loguru import logger

from app.config import settings
from app.exceptions.handler import ServiceException


def delete_all_spots_for_owner(owner_id: UUID) -> None:
    """Hard-deletes every parking spot (and their R2 photos) owned by this
    user -- called only from delete_user, when the account is closed for
    good. Direct service-to-service call on the docker network, same
    convention as parking-service's own BookingClientService: no gateway
    route, authenticated with the shared INTERNAL_SERVICE_KEY.

    Raises on any failure instead of best-effort swallowing it: this runs
    before the user row itself is deleted, so failing loudly here means the
    account deletion aborts with nothing destroyed yet, rather than silently
    leaving orphaned spots/photos behind with no user left to retry against.
    """
    url = f"{settings.PARKING_SERVICE_URL}/users/{owner_id}/parking-spots"

    try:
        response = httpx.delete(
            url,
            headers={"X-Internal-Key": settings.INTERNAL_SERVICE_KEY},
            timeout=10.0,
        )
    except httpx.HTTPError as e:
        logger.error(f"[USERS] Error de red borrando cocheras de owner_id={owner_id}: {e}")
        raise ServiceException(
            status_code=502, title="Bad Gateway", detail="Could not reach parking-service."
        )

    if response.status_code >= 400:
        logger.error(
            f"[USERS] parking-service devolvió status={response.status_code} "
            f"borrando cocheras de owner_id={owner_id}: {response.text}"
        )
        raise ServiceException(
            status_code=502, title="Bad Gateway", detail="Failed to delete owner's parking spots."
        )
