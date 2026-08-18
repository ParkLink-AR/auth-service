from __future__ import annotations

from uuid import uuid4

from loguru import logger
from sqlalchemy.orm import Session

from app import models, schemas, security
from app.exceptions.handler import ServiceException
from app.models import UserStatus
from app.repositories import tokens as tokens_repository
from app.repositories import users as users_repository
from app.services.auth_service import issue_email_verification_code
from app.utils.email import send_verification_email


def _require_self(user_id, current_user: models.User) -> None:
    if current_user.id != user_id:
        raise ServiceException(
            status_code=403, title="Forbidden", detail="You can only access your own account."
        )


def get_user(user_id, current_user: models.User) -> models.User:
    _require_self(user_id, current_user)
    return current_user


def update_user(user_id, payload: schemas.UserUpdate, db: Session, current_user: models.User) -> models.User:
    _require_self(user_id, current_user)

    update_data = payload.model_dump(exclude_unset=True)

    if "email" in update_data and update_data["email"] != current_user.email:
        new_email = update_data["email"]
        if users_repository.get_by_email(db, new_email):
            raise ServiceException(
                status_code=400, title="Bad Request", detail="Email is already registered."
            )
        current_user.email = new_email
        current_user.email_verified = False

        code = issue_email_verification_code(db, current_user)
        send_verification_email(to_email=new_email, code=code)

    if "first_name" in update_data:
        current_user.first_name = update_data["first_name"]

    if "last_name" in update_data:
        current_user.last_name = update_data["last_name"]

    if "phone" in update_data and update_data["phone"] != current_user.phone:
        new_phone = update_data["phone"]
        if new_phone and users_repository.get_by_phone(db, new_phone):
            raise ServiceException(
                status_code=400, title="Bad Request", detail="Phone is already registered."
            )
        current_user.phone = new_phone
        current_user.phone_verified = False

    try:
        users_repository.save(db, current_user)
    except Exception as e:
        db.rollback()
        logger.error(f"[USERS] Error actualizando user_id={current_user.id}: {e}")
        raise ServiceException(
            status_code=500, title="Internal Server Error", detail="Error updating user."
        )

    logger.info(f"[USERS] Perfil actualizado: user_id={current_user.id}")
    return current_user


def delete_user(user_id, payload: schemas.AccountDeleteRequest, db: Session, current_user: models.User) -> dict:
    _require_self(user_id, current_user)

    if not security.verify_password(payload.password, current_user.password_hash):
        raise ServiceException(
            status_code=401, title="Unauthorized", detail="Incorrect password."
        )

    current_user.status = UserStatus.DELETED
    current_user.email = f"deleted-{uuid4().hex}@deleted.parklink.app"
    current_user.phone = None
    current_user.password_hash = security.hash_password(uuid4().hex)
    users_repository.save(db, current_user)

    tokens_repository.revoke_all_for_user(db, current_user.id)

    logger.info(f"[USERS] Cuenta eliminada: user_id={current_user.id}")
    return {"message": "Account deleted successfully."}
