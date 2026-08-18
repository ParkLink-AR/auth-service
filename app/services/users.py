from __future__ import annotations

import secrets
from uuid import uuid4

from loguru import logger
from sqlalchemy.orm import Session

from app import models, schemas, security
from app.config import settings
from app.exceptions.handler import ServiceException
from app.models import UserStatus, VerificationTokenType
from app.repositories import tokens as tokens_repository
from app.repositories import users as users_repository
from app.services import auth_service
from app.utils.email import send_email_change_email
from app.utils.sms import send_registration_sms


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

    if "first_name" in update_data:
        current_user.first_name = update_data["first_name"]

    if "last_name" in update_data:
        current_user.last_name = update_data["last_name"]

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


# -------------------------
# Email change (request the new address, confirm with the code sent to it)
# -------------------------


def request_email_change(
    user_id, payload: schemas.EmailChangeRequest, db: Session, current_user: models.User
) -> dict:
    _require_self(user_id, current_user)

    new_email = payload.new_email
    if new_email == current_user.email:
        raise ServiceException(
            status_code=400, title="Bad Request", detail="That's already your current email."
        )
    if users_repository.get_by_email(db, new_email):
        raise ServiceException(
            status_code=400, title="Bad Request", detail="Email is already registered."
        )

    auth_service._check_rate_limit(
        db, current_user.id, VerificationTokenType.EMAIL_CHANGE, "requesting another code"
    )
    code = auth_service.issue_code_for_user(
        db,
        current_user.id,
        VerificationTokenType.EMAIL_CHANGE,
        settings.EMAIL_VERIFICATION_CODE_EXPIRE_MINUTES,
    )
    current_user.pending_email = new_email
    users_repository.save(db, current_user)

    send_email_change_email(to_email=new_email, code=code)
    logger.info(f"[USERS] Código de cambio de email enviado: user_id={current_user.id}")
    return {"message": "Verification code sent to the new email."}


def confirm_email_change(
    user_id, payload: schemas.EmailChangeConfirm, db: Session, current_user: models.User
) -> models.User:
    _require_self(user_id, current_user)

    invalid_code_error = ServiceException(
        status_code=400, title="Bad Request", detail="Invalid or expired verification code."
    )

    if not current_user.pending_email:
        raise ServiceException(
            status_code=400, title="Bad Request", detail="No pending email change."
        )

    token = tokens_repository.get_active_verification_token_for_user(
        db, current_user.id, VerificationTokenType.EMAIL_CHANGE
    )
    if not token:
        raise invalid_code_error

    if token.attempts >= auth_service._MAX_VERIFICATION_ATTEMPTS:
        tokens_repository.mark_used(db, token)
        raise ServiceException(
            status_code=400,
            title="Bad Request",
            detail="Too many incorrect attempts. Request a new code.",
        )

    if not secrets.compare_digest(security.hash_token(payload.code), token.token_hash):
        attempts = tokens_repository.increment_attempts(db, token)
        remaining = max(auth_service._MAX_VERIFICATION_ATTEMPTS - attempts, 0)
        raise ServiceException(
            status_code=400,
            title="Bad Request",
            detail=f"Invalid verification code. {remaining} attempts remaining.",
        )

    # Someone else could have claimed this email while the code was in flight.
    if users_repository.get_by_email(db, current_user.pending_email):
        current_user.pending_email = None
        users_repository.save(db, current_user)
        raise ServiceException(
            status_code=400, title="Bad Request", detail="Email is already registered."
        )

    current_user.email = current_user.pending_email
    current_user.pending_email = None
    current_user.email_verified = True
    tokens_repository.mark_used(db, token)
    users_repository.save(db, current_user)

    logger.info(f"[USERS] Email actualizado: user_id={current_user.id}")
    return current_user


# -------------------------
# Phone change (request the new number, confirm with the SMS code sent to it)
# -------------------------


def request_phone_change(
    user_id, payload: schemas.PhoneChangeRequest, db: Session, current_user: models.User
) -> dict:
    _require_self(user_id, current_user)

    new_phone = payload.new_phone
    if new_phone == current_user.phone:
        raise ServiceException(
            status_code=400, title="Bad Request", detail="That's already your current phone."
        )
    if users_repository.get_by_phone(db, new_phone):
        raise ServiceException(
            status_code=400, title="Bad Request", detail="Phone is already registered."
        )

    auth_service._check_rate_limit(
        db, current_user.id, VerificationTokenType.PHONE_CHANGE, "requesting another code"
    )
    code = auth_service.issue_code_for_user(
        db,
        current_user.id,
        VerificationTokenType.PHONE_CHANGE,
        settings.PHONE_VERIFICATION_CODE_EXPIRE_MINUTES,
    )
    current_user.pending_phone = new_phone
    users_repository.save(db, current_user)

    send_registration_sms(to_phone=new_phone, code=code)
    logger.info(f"[USERS] Código de cambio de teléfono enviado: user_id={current_user.id}")
    return {"message": "Verification code sent to the new phone."}


def confirm_phone_change(
    user_id, payload: schemas.PhoneChangeConfirm, db: Session, current_user: models.User
) -> models.User:
    _require_self(user_id, current_user)

    invalid_code_error = ServiceException(
        status_code=400, title="Bad Request", detail="Invalid or expired verification code."
    )

    if not current_user.pending_phone:
        raise ServiceException(
            status_code=400, title="Bad Request", detail="No pending phone change."
        )

    token = tokens_repository.get_active_verification_token_for_user(
        db, current_user.id, VerificationTokenType.PHONE_CHANGE
    )
    if not token:
        raise invalid_code_error

    if token.attempts >= auth_service._MAX_VERIFICATION_ATTEMPTS:
        tokens_repository.mark_used(db, token)
        raise ServiceException(
            status_code=400,
            title="Bad Request",
            detail="Too many incorrect attempts. Request a new code.",
        )

    if not secrets.compare_digest(security.hash_token(payload.code), token.token_hash):
        attempts = tokens_repository.increment_attempts(db, token)
        remaining = max(auth_service._MAX_VERIFICATION_ATTEMPTS - attempts, 0)
        raise ServiceException(
            status_code=400,
            title="Bad Request",
            detail=f"Invalid verification code. {remaining} attempts remaining.",
        )

    if users_repository.get_by_phone(db, current_user.pending_phone):
        current_user.pending_phone = None
        users_repository.save(db, current_user)
        raise ServiceException(
            status_code=400, title="Bad Request", detail="Phone is already registered."
        )

    current_user.phone = current_user.pending_phone
    current_user.pending_phone = None
    current_user.phone_verified = True
    tokens_repository.mark_used(db, token)
    users_repository.save(db, current_user)

    logger.info(f"[USERS] Teléfono actualizado: user_id={current_user.id}")
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
