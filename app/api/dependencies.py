from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, security
from app.exceptions.handler import ServiceException
from app.services import account_lifecycle


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

    # Only an active account can use its session -- a suspended or closing one is out
    # even with a still-valid token, with the same coded reason the login gives (e.g.
    # ACCOUNT_SUSPENDED), so the app can log it out and say why.
    account_lifecycle.ensure_can_log_in(user)

    return user
