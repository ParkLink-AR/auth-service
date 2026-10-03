from __future__ import annotations
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.dependencies import get_current_user
from app.database import get_db
from app.services import users as users_service
from app.services import vehicles as vehicles_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/{id}/public-profile", response_model=schemas.PublicUserOut)
def get_public_profile(
    id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return users_service.get_public_profile(id, db)


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


@router.get("/{id}/payout-info", response_model=schemas.PayoutInfoOut)
def get_payout_info(
    id: UUID,
    current_user: models.User = Depends(get_current_user),
):
    return users_service.get_payout_info(id, current_user)


@router.put("/{id}/payout-info", response_model=schemas.PayoutInfoOut)
def update_payout_info(
    id: UUID,
    payload: schemas.PayoutInfoUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return users_service.update_payout_info(id, payload, db, current_user)


@router.post("/{id}/password/verify", response_model=dict)
def verify_current_password(
    id: UUID,
    payload: schemas.PasswordVerifyRequest,
    current_user: models.User = Depends(get_current_user),
):
    return users_service.verify_current_password(id, payload, current_user)


@router.put("/{id}/password", response_model=dict)
def change_password(
    id: UUID,
    payload: schemas.PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return users_service.change_password(id, payload, db, current_user)


@router.post("/{id}/avatar", response_model=schemas.UserOut)
async def update_avatar(
    id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return await users_service.update_avatar(id, file, db, current_user)


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


@router.get("/{id}/vehicles", response_model=list[schemas.VehicleOut])
def list_vehicles(
    id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return vehicles_service.list_vehicles(id, db, current_user)


@router.post("/{id}/vehicles", response_model=schemas.VehicleOut, status_code=201)
def create_vehicle(
    id: UUID,
    payload: schemas.VehicleCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return vehicles_service.create_vehicle(id, payload, db, current_user)


@router.delete("/{id}/vehicles/{vehicle_id}", response_model=dict)
def delete_vehicle(
    id: UUID,
    vehicle_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    vehicles_service.delete_vehicle(id, vehicle_id, db, current_user)
    return {"deleted": True}
