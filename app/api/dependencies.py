from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, security
from app.exceptions.handler import ServiceException
from app.models import UserStatus


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> models.User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ServiceException(
            status_code=401, title="Unauthorized", detail="Missing token"
        )

    token = authorization.split(maxsplit=1)[1]
    data = security.decode_access_token(token)

    if not data:
        raise ServiceException(
            status_code=401, title="Unauthorized", detail="Invalid token"
        )

    user_id = data.get("sub")
    if user_id is None:
        raise ServiceException(
            status_code=401,
            title="Unauthorized",
            detail="Invalid token: missing user id",
        )

    try:
        user = db.get(models.User, UUID(user_id))
    except ValueError:
        user = None

    if not user:
        raise ServiceException(
            status_code=404, title="Not Found", detail="User not found"
        )

    if user.status != UserStatus.ACTIVE:
        raise ServiceException(
            status_code=403, title="Forbidden", detail="This account is not active."
        )

    return user
