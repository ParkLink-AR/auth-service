from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from app.config import settings
from app.exceptions.handler import ServiceException


def call_internal(method: str, url: str, action: str, json: Any | None = None) -> Any:
    """Service-to-service call on the docker network (no gateway), authenticated with the
    shared INTERNAL_SERVICE_KEY. Raises a 502 on any network or HTTP error instead of
    swallowing it: the account lifecycle runs these before committing its own change, so
    failing loudly leaves the account as it was for the caller to retry."""
    try:
        response = httpx.request(
            method,
            url,
            json=json,
            headers={"X-Internal-Key": settings.INTERNAL_SERVICE_KEY},
            timeout=15.0,
        )
    except httpx.HTTPError as e:
        logger.error(f"[INTERNAL] Error de red ({action}): {e}")
        raise ServiceException(status_code=502, title="Bad Gateway", detail=f"Could not {action}.")

    if response.status_code >= 400:
        logger.error(f"[INTERNAL] status={response.status_code} ({action}): {response.text}")
        raise ServiceException(status_code=502, title="Bad Gateway", detail=f"Could not {action}.")

    if response.status_code == 204 or not response.content:
        return None
    return response.json()
