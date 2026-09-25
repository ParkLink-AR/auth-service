from uuid import UUID

from sqlalchemy.orm import Session

from app import models


def get_by_username(db: Session, username: str) -> models.AdminAccount | None:
    return db.query(models.AdminAccount).filter(models.AdminAccount.username == username).first()


def get_by_id(db: Session, admin_id: UUID) -> models.AdminAccount | None:
    return db.get(models.AdminAccount, admin_id)


def create(db: Session, admin_account: models.AdminAccount) -> models.AdminAccount:
    db.add(admin_account)
    db.flush()
    return admin_account


def list_all(db: Session) -> list[models.AdminAccount]:
    return db.query(models.AdminAccount).order_by(models.AdminAccount.created_at.asc()).all()


def set_active(db: Session, admin_account: models.AdminAccount, is_active: bool) -> models.AdminAccount:
    admin_account.is_active = is_active
    db.add(admin_account)
    db.commit()
    db.refresh(admin_account)
    return admin_account


def set_password_hash(db: Session, admin_account: models.AdminAccount, password_hash: str) -> models.AdminAccount:
    admin_account.password_hash = password_hash
    db.add(admin_account)
    db.commit()
    db.refresh(admin_account)
    return admin_account
