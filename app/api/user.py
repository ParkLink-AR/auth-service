from __future__ import annotations
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.dependencies import get_current_user
from app.database import get_db
from app.services import users as users_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/{id}", response_model=schemas.UserOut)
def get_user(
    id: UUID,
    current_user: models.User = Depends(get_current_user),
):
    return users_service.get_user(id, current_user)


@router.put("/{id}", response_model=schemas.UserOut)
def update_user(
    id: UUID,
    payload: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return users_service.update_user(id, payload, db, current_user)


@router.post("/{id}/email", response_model=dict)
def request_email_change(
    id: UUID,
    payload: schemas.EmailChangeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return users_service.request_email_change(id, payload, db, current_user)


@router.post("/{id}/email/confirm", response_model=schemas.UserOut)
def confirm_email_change(
    id: UUID,
    payload: schemas.EmailChangeConfirm,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return users_service.confirm_email_change(id, payload, db, current_user)


@router.post("/{id}/phone", response_model=dict)
def request_phone_change(
    id: UUID,
    payload: schemas.PhoneChangeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return users_service.request_phone_change(id, payload, db, current_user)


@router.post("/{id}/phone/confirm", response_model=schemas.UserOut)
def confirm_phone_change(
    id: UUID,
    payload: schemas.PhoneChangeConfirm,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return users_service.confirm_phone_change(id, payload, db, current_user)


@router.delete("/{id}", response_model=dict)
def delete_user(
    id: UUID,
    payload: schemas.AccountDeleteRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return users_service.delete_user(id, payload, db, current_user)
