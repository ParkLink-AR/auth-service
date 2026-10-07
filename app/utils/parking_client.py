from __future__ import annotations

from uuid import UUID

from app.config import settings
from app.utils.internal_http import call_internal


def _owner_url(owner_id: UUID, action: str) -> str:
    return f"{settings.PARKING_SERVICE_URL}/internal/owners/{owner_id}/parking-spots/{action}"


def pause_owner_spots(owner_id: UUID) -> list[str]:
    """Takes every spot of this owner out of search while their account is suspended or
    being deleted (marked as paused by the account, so restore_owner_spots brings back
    exactly those). Returns the ids of all the owner's (non-deleted) spots."""
    response = call_internal("POST", _owner_url(owner_id, "pause"), "pause the owner's parking spots")
    return list(response.get("spot_ids", [])) if response else []


def restore_owner_spots(owner_id: UUID) -> None:
    """Undoes pause_owner_spots once the account is active again."""
    call_internal("POST", _owner_url(owner_id, "restore"), "restore the owner's parking spots")


def archive_owner_spots(owner_id: UUID) -> None:
    """Marks every spot of this owner as deleted and drops its photos and documentation --
    the last step of deleting the account. The rows stay for the bookings that point at them."""
    call_internal("POST", _owner_url(owner_id, "archive"), "archive the owner's parking spots")


def list_owner_spot_ids(owner_id: UUID) -> list[str]:
    response = call_internal(
        "GET", f"{settings.PARKING_SERVICE_URL}/users/{owner_id}/parking-spots", "list the owner's parking spots"
    )
    return [spot["id"] for spot in response or []]
