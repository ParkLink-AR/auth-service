from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from loguru import logger
from sqlalchemy.orm import Session

from app import models, schemas, security
from app.config import settings
from app.exceptions.handler import ServiceException
from app.models import UserStatus, VerificationTokenType
from app.repositories import tokens as tokens_repository
from app.repositories import users as users_repository
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

        tokens_repository.invalidate_active_tokens(db, current_user.id, VerificationTokenType.EMAIL)
        raw_token = security.generate_opaque_token()
        token = models.VerificationToken(
            user_id=current_user.id,
            type=VerificationTokenType.EMAIL,
            token_hash=security.hash_token(raw_token),
            expires_at=datetime.now(timezone.utc)
            + timedelta(hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS),
        )
        tokens_repository.create_verification_token(db, token)
        send_verification_email(to_email=new_email, verification_token=raw_token)

    if "phone" in update_data and update_data["phone"] != current_user.phone:
        new_phone = update_data["phone"]
        if new_phone and users_repository.get_by_phone(db, new_phone):
            raise ServiceException(
                status_code=400, title="Bad Request", detail="Phone is already registered."
            )
        current_user.phone = new_phone
        current_user.phone_verified = False

    for field in ("first_name", "last_name", "avatar_url"):
        if field in update_data:
            setattr(current_user, field, update_data[field])

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
