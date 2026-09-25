from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models


def get_by_id(db: Session, user_id: UUID) -> models.User | None:
    return db.get(models.User, user_id)


def search(db: Session, query: str, limit: int = 50) -> list[models.User]:
    """Case-insensitive partial match across the fields ParkLink staff would
    plausibly search a user by. Used only from the admin router (app/api/
    admin.py), which the gateway gates on the `role: admin` JWT claim."""
    pattern = f"%{query}%"
    return (
        db.query(models.User)
        .filter(
            or_(
                models.User.email.ilike(pattern),
                models.User.phone.ilike(pattern),
                models.User.dni.ilike(pattern),
                models.User.first_name.ilike(pattern),
                models.User.last_name.ilike(pattern),
            )
        )
        .limit(limit)
        .all()
    )


def get_by_email(db: Session, email: str) -> models.User | None:
    return db.query(models.User).filter(models.User.email == email).first()


def get_by_phone(db: Session, phone: str) -> models.User | None:
    return db.query(models.User).filter(models.User.phone == phone).first()


def get_by_dni(db: Session, dni: str) -> models.User | None:
    return db.query(models.User).filter(models.User.dni == dni).first()


def create(db: Session, user: models.User) -> models.User:
    db.add(user)
    db.flush()
    return user


def save(db: Session, user: models.User) -> models.User:
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
