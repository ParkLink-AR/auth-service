from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app import models
from app.exceptions.handler import ServiceException
from app.repositories import users as users_repository

_MAX_SEARCH_RESULTS = 50


def search_users(db: Session, query: str) -> list[models.User]:
    return users_repository.search(db, query, limit=_MAX_SEARCH_RESULTS)


def get_user_detail(db: Session, user_id: UUID) -> models.User:
    user = users_repository.get_by_id(db, user_id)
    if not user:
        raise ServiceException(status_code=404, title="Not Found", detail="User not found.")
    return user
