from uuid import UUID

from sqlalchemy.orm import Session

from app import models


def list_by_user(db: Session, user_id: UUID) -> list[models.Vehicle]:
    return (
        db.query(models.Vehicle)
        .filter(models.Vehicle.user_id == user_id)
        .order_by(models.Vehicle.created_at.asc())
        .all()
    )


def get_by_id(db: Session, vehicle_id: UUID) -> models.Vehicle | None:
    return db.get(models.Vehicle, vehicle_id)


def create(db: Session, vehicle: models.Vehicle) -> models.Vehicle:
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


def delete(db: Session, vehicle: models.Vehicle) -> None:
    db.delete(vehicle)
    db.commit()
