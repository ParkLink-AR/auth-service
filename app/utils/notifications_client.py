from __future__ import annotations

from uuid import UUID

from app.config import settings
from app.utils.internal_http import call_internal


def delete_device_tokens(user_id: UUID) -> None:
    """Stops push notifications to every device of this user."""
    call_internal(
        "DELETE",
        f"{settings.NOTIFICATIONS_SERVICE_URL}/internal/users/{user_id}/device-tokens",
        "delete the user's push tokens",
    )
