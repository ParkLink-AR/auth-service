from __future__ import annotations

from typing import Any
from uuid import UUID

from loguru import logger

from app.config import settings
from app.utils.internal_http import call_internal


def _payload(user_id: UUID, spot_ids: list[str]) -> dict[str, Any]:
    return {"user_id": str(user_id), "spot_ids": spot_ids}


def get_account_closure_summary(user_id: UUID, spot_ids: list[str]) -> dict[str, Any]:
    """What closing this account would touch in booking-service: bookings in progress
    (which block it), bookings that would be cancelled, and money still owed to the owner."""
    return call_internal(
        "POST",
        f"{settings.BOOKING_SERVICE_URL}/internal/account-closure/summary",
        "get the account's bookings summary",
        json=_payload(user_id, spot_ids),
    )


def cancel_account_bookings(user_id: UUID, spot_ids: list[str]) -> dict[str, Any]:
    """Cancels, with a full refund, every booking of this account that hasn't started yet
    (as a driver, and on its spots as an owner), and drops its pending payment holds."""
    result = call_internal(
        "POST",
        f"{settings.BOOKING_SERVICE_URL}/internal/account-closure/cancel-bookings",
        "cancel the account's bookings",
        json=_payload(user_id, spot_ids),
    ) or {}
    if result.get("refund_failures"):
        # Cancelled, but the refund didn't go through -- needs a manual refund.
        logger.error(
            f"[ACCOUNT] Reembolsos fallidos al cerrar la cuenta user_id={user_id}: {result['refund_failures']}"
        )
    return result


def anonymize_account_bookings(user_id: UUID) -> None:
    """Wipes the personal data booking-service copied onto the driver's bookings (the
    vehicle snapshot) -- the bookings themselves stay."""
    call_internal(
        "POST",
        f"{settings.BOOKING_SERVICE_URL}/internal/account-closure/anonymize",
        "anonymize the account's bookings",
        json={"user_id": str(user_id)},
    )
