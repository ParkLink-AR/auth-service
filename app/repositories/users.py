from uuid import UUID

from sqlalchemy.orm import Session

from app import models


def get_by_id(db: Session, user_id: UUID) -> models.User | None:
    return db.get(models.User, user_id)


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
