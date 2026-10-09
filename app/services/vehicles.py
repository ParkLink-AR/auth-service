from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app import models, schemas
from app.exceptions.handler import ServiceException
from app.repositories import vehicles as vehicles_repository


def _require_self(user_id, current_user: models.User) -> None:
    if current_user.id != user_id:
        raise ServiceException(
            status_code=403, title="Forbidden", detail="You can only access your own account."
        )


def list_vehicles(user_id, db: Session, current_user: models.User) -> list[models.Vehicle]:
    _require_self(user_id, current_user)
    return vehicles_repository.list_by_user(db, user_id)


def create_vehicle(
    user_id, payload: schemas.VehicleCreate, db: Session, current_user: models.User
) -> models.Vehicle:
    _require_self(user_id, current_user)
    vehicle = models.Vehicle(
        user_id=user_id,
        type=payload.type,
        plate=payload.plate,
        brand=payload.brand,
        model=payload.model,
        country=payload.country,
    )
    return vehicles_repository.create(db, vehicle)


def update_vehicle_type(
    user_id, vehicle_id: UUID, payload: schemas.VehicleTypeUpdate, db: Session, current_user: models.User
) -> models.Vehicle:
    _require_self(user_id, current_user)
    vehicle = vehicles_repository.get_by_id(db, vehicle_id)
    if vehicle is None or vehicle.user_id != user_id:
        raise ServiceException(status_code=404, title="Not Found", detail="Vehicle not found.")
    vehicle.type = payload.type
    return vehicles_repository.save(db, vehicle)


def delete_vehicle(user_id, vehicle_id: UUID, db: Session, current_user: models.User) -> None:
    _require_self(user_id, current_user)
    vehicle = vehicles_repository.get_by_id(db, vehicle_id)
    if vehicle is None or vehicle.user_id != user_id:
        raise ServiceException(status_code=404, title="Not Found", detail="Vehicle not found.")
    vehicles_repository.delete(db, vehicle)
