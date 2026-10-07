from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Request
from loguru import logger
from sqlalchemy.orm import Session

from app import models, schemas, security
from app.config import settings
from app.exceptions.handler import ServiceException
from app.models import VerificationTokenType
from app.services import account_lifecycle
from app.repositories import registration_verifications as registration_verifications_repository
from app.repositories import tokens as tokens_repository
from app.repositories import users as users_repository
from app.utils.email import send_reset_password_email, send_verification_email
from app.utils.sms import send_registration_sms

_RATE_LIMIT_SECONDS = 60
_MAX_VERIFICATION_ATTEMPTS = 5


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _check_rate_limit(db: Session, user_id: UUID, token_type: VerificationTokenType, context: str) -> None:
    latest = tokens_repository.get_latest_token(db, user_id, token_type)
    if latest is None:
        return
    elapsed = (datetime.now(timezone.utc) - latest.created_at.replace(tzinfo=timezone.utc)).total_seconds()
    if elapsed < _RATE_LIMIT_SECONDS:
        wait = int(_RATE_LIMIT_SECONDS - elapsed)
        raise ServiceException(
            status_code=429,
            title="Too Many Requests",
            detail=f"Please wait before {context}. Try again in {wait} seconds.",
        )


def issue_code_for_user(
    db: Session, user_id: UUID, token_type: VerificationTokenType, expire_minutes: int
) -> str:
    """Issues a 6-digit code of the given type for an existing user
    (invalidating any previous active one of the same type first)."""
    tokens_repository.invalidate_active_tokens(db, user_id, token_type)
    code = security.generate_numeric_code()
    token = models.VerificationToken(
        user_id=user_id,
        type=token_type,
        token_hash=security.hash_token(code),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=expire_minutes),
    )
    tokens_repository.create_verification_token(db, token)
    return code


def issue_email_verification_code(db: Session, user: models.User) -> str:
    """Issues a 6-digit email verification code, used both at registration
    and on-demand resend."""
    return issue_code_for_user(
        db, user.id, VerificationTokenType.EMAIL, settings.EMAIL_VERIFICATION_CODE_EXPIRE_MINUTES
    )


def _issue_token_pair(db: Session, user: models.User, device: schemas.DeviceInfo, request: Request | None) -> schemas.Token:
    raw_refresh_token = security.generate_opaque_token()
    refresh_token = models.RefreshToken(
        user_id=user.id,
        token_hash=security.hash_token(raw_refresh_token),
        device_id=device.device_id,
        device_name=device.device_name,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        ip_address=_client_ip(request),
    )
    tokens_repository.create_refresh_token(db, refresh_token)
    db.commit()

    access_token = security.create_access_token(user.id)

    return schemas.Token(
        access_token=access_token,
        refresh_token=raw_refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# -------------------------
# Registration wizard: verify email, then phone, THEN create the account
# (both channels already verified at creation time -- no post-signup
# "confirm your email" step for new signups anymore).
# -------------------------


def _check_registration_rate_limit(
    db: Session, verification_type: VerificationTokenType, target: str, context: str
) -> None:
    latest = registration_verifications_repository.get_latest_for_target(db, verification_type, target)
    if latest is None:
        return
    elapsed = (datetime.now(timezone.utc) - latest.created_at.replace(tzinfo=timezone.utc)).total_seconds()
    if elapsed < _RATE_LIMIT_SECONDS:
        wait = int(_RATE_LIMIT_SECONDS - elapsed)
        raise ServiceException(
            status_code=429,
            title="Too Many Requests",
            detail=f"Please wait before {context}. Try again in {wait} seconds.",
        )


def _issue_registration_code(
    db: Session, verification_type: VerificationTokenType, target: str, expire_minutes: int
) -> str:
    code = security.generate_numeric_code()
    verification = models.RegistrationVerification(
        type=verification_type,
        target=target,
        token_hash=security.hash_token(code),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=expire_minutes),
    )
    registration_verifications_repository.create(db, verification)
    return code


def _confirm_registration_code(
    db: Session, verification_type: VerificationTokenType, target: str, code: str
) -> None:
    invalid_code_error = ServiceException(
        status_code=400, title="Bad Request", detail="Invalid or expired verification code."
    )

    verification = registration_verifications_repository.get_active_for_target(db, verification_type, target)
    if not verification:
        raise invalid_code_error

    if verification.attempts >= _MAX_VERIFICATION_ATTEMPTS:
        registration_verifications_repository.mark_used(db, verification)
        raise ServiceException(
            status_code=400,
            title="Bad Request",
            detail="Too many incorrect attempts. Request a new code.",
        )

    if not secrets.compare_digest(security.hash_token(code), verification.token_hash):
        attempts = registration_verifications_repository.increment_attempts(db, verification)
        remaining = max(_MAX_VERIFICATION_ATTEMPTS - attempts, 0)
        raise ServiceException(
            status_code=400,
            title="Bad Request",
            detail=f"Invalid verification code. {remaining} attempts remaining.",
        )

    registration_verifications_repository.mark_verified(
        db, verification, timedelta(minutes=settings.REGISTRATION_VERIFICATION_GRACE_MINUTES)
    )


def request_email_registration(payload: schemas.EmailVerificationRequest, db: Session) -> dict:
    account_lifecycle.ensure_identifier_available(
        users_repository.get_by_email(db, payload.email), "Email is already registered."
    )

    # Verified a moment ago (still within the grace period) and coming back to the
    # wizard, e.g. after closing the app: no need for another code.
    if registration_verifications_repository.get_verified_for_target(db, VerificationTokenType.EMAIL, payload.email):
        return {"message": "Email already verified.", "already_verified": True}

    _check_registration_rate_limit(
        db, VerificationTokenType.EMAIL, payload.email, "requesting another code"
    )
    code = _issue_registration_code(
        db, VerificationTokenType.EMAIL, payload.email, settings.EMAIL_VERIFICATION_CODE_EXPIRE_MINUTES
    )
    send_verification_email(to_email=payload.email, code=code)
    logger.info(f"[AUTH] Código de registro (email) enviado a {payload.email}")
    return {"message": "Verification code sent.", "already_verified": False}


def confirm_email_registration(payload: schemas.EmailVerificationConfirm, db: Session) -> dict:
    _confirm_registration_code(db, VerificationTokenType.EMAIL, payload.email, payload.code)
    logger.info(f"[AUTH] Email verificado (pre-registro): {payload.email}")
    return {"message": "Email verified successfully."}


def request_phone_registration(payload: schemas.PhoneRegistrationRequest, db: Session) -> dict:
    account_lifecycle.ensure_identifier_available(
        users_repository.get_by_phone(db, payload.phone), "Phone is already registered."
    )

    if registration_verifications_repository.get_verified_for_target(db, VerificationTokenType.PHONE, payload.phone):
        return {"message": "Phone already verified.", "already_verified": True}

    _check_registration_rate_limit(
        db, VerificationTokenType.PHONE, payload.phone, "requesting another code"
    )
    code = _issue_registration_code(
        db, VerificationTokenType.PHONE, payload.phone, settings.PHONE_VERIFICATION_CODE_EXPIRE_MINUTES
    )
    send_registration_sms(to_phone=payload.phone, code=code)
    logger.info(f"[AUTH] Código de registro (teléfono) enviado a {payload.phone}")
    return {"message": "Verification code sent.", "already_verified": False}


def confirm_phone_registration(payload: schemas.PhoneRegistrationConfirm, db: Session) -> dict:
    _confirm_registration_code(db, VerificationTokenType.PHONE, payload.phone, payload.code)
    logger.info(f"[AUTH] Teléfono verificado (pre-registro): {payload.phone}")
    return {"message": "Phone verified successfully."}


# -------------------------
# Register
# -------------------------


def register(payload: schemas.UserCreate, db: Session) -> models.User:
    logger.debug(f"[AUTH] Intento de registro: email={payload.email}")

    account_lifecycle.ensure_identifier_available(
        users_repository.get_by_email(db, payload.email), "Email is already registered."
    )
    account_lifecycle.ensure_identifier_available(
        users_repository.get_by_phone(db, payload.phone), "Phone is already registered."
    )
    account_lifecycle.ensure_identifier_available(
        users_repository.get_by_dni(db, payload.dni), "DNI is already registered."
    )

    email_verification = None
    if not settings.SKIP_EMAIL_VERIFICATION:
        email_verification = registration_verifications_repository.get_verified_for_target(
            db, VerificationTokenType.EMAIL, payload.email
        )
        if not email_verification:
            raise ServiceException(
                status_code=400, title="Bad Request", detail="Email is not verified yet."
            )

    phone_verification = None
    if not settings.SKIP_PHONE_VERIFICATION:
        phone_verification = registration_verifications_repository.get_verified_for_target(
            db, VerificationTokenType.PHONE, payload.phone
        )
        if not phone_verification:
            raise ServiceException(
                status_code=400, title="Bad Request", detail="Phone is not verified yet."
            )

    user = models.User(
        email=payload.email,
        phone=payload.phone,
        first_name=payload.first_name,
        last_name=payload.last_name,
        dni=payload.dni,
        birth_date=payload.birth_date,
        password_hash=security.hash_password(payload.password),
        # email_verified is always True here: either the code was confirmed
        # above, or SKIP_EMAIL_VERIFICATION bypassed the requirement.
        # phone_verified reflects reality -- SKIP_PHONE_VERIFICATION lets the
        # account exist with an unconfirmed phone number (see config.py).
        email_verified=True,
        phone_verified=phone_verification is not None,
        account_type=payload.account_type,
    )

    try:
        users_repository.create(db, user)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(user)

    if email_verification:
        registration_verifications_repository.mark_used(db, email_verification)
    if phone_verification:
        registration_verifications_repository.mark_used(db, phone_verification)

    logger.info(f"[AUTH] Usuario registrado: id={user.id}, email={user.email}")
    return user


# -------------------------
# Login / refresh / logout
# -------------------------


def _authenticate(payload: schemas.UserLogin, db: Session) -> models.User:
    user = users_repository.get_by_email(db, payload.email) if payload.email else None
    if user is None and payload.phone:
        user = users_repository.get_by_phone(db, payload.phone)

    if not user or not security.verify_password(payload.password, user.password_hash):
        raise ServiceException(
            status_code=401, title="Unauthorized", detail="Invalid credentials."
        )
    return user


def login(payload: schemas.UserLogin, db: Session, request: Request | None = None) -> schemas.Token:
    logger.debug(f"[AUTH] Intento de login: email={payload.email}, phone={payload.phone}")

    user = _authenticate(payload, db)

    # Only an active account gets a session. Suspended or deleted ones get the reason; one
    # waiting out a deletion the user asked for gets ACCOUNT_DELETION_SCHEDULED, which the
    # app answers by offering to reactivate it (reactivate_and_log_in below).
    account_lifecycle.ensure_can_log_in(user)

    return _finish_login(db, user, payload, request)


def reactivate_and_log_in(payload: schemas.UserLogin, db: Session, request: Request | None = None) -> schemas.Token:
    """Cancels a deletion the user asked for (still within its grace period) and logs them
    in -- the "yes, reactivate it" answer to ACCOUNT_DELETION_SCHEDULED. Same credentials
    as the login, since there's no session yet to prove who they are."""
    user = _authenticate(payload, db)
    if not account_lifecycle.can_cancel_deletion(user):
        account_lifecycle.ensure_can_log_in(user)
        raise ServiceException(
            status_code=409, title="Conflict", detail="Tu cuenta no tiene una eliminación para cancelar."
        )
    account_lifecycle.cancel_deletion(db, user)
    return _finish_login(db, user, payload, request)


def _finish_login(db: Session, user: models.User, payload: schemas.UserLogin, request: Request | None) -> schemas.Token:
    if not settings.SKIP_EMAIL_VERIFICATION and not user.email_verified:
        raise ServiceException(
            status_code=403,
            title="Forbidden",
            detail="Please verify your email before logging in.",
        )

    user.last_login_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()

    token = _issue_token_pair(db, user, payload, request)
    logger.info(f"[AUTH] Login exitoso: id={user.id}")
    return token


def refresh(payload: schemas.RefreshRequest, db: Session, request: Request | None = None) -> schemas.Token:
    token_hash = security.hash_token(payload.refresh_token)
    existing = tokens_repository.get_refresh_token_by_hash(db, token_hash)

    # Suspended or closing meanwhile (which also revoked this token): the coded reason
    # first, not a bare 401, so the app can tell the user why they were logged out.
    user = users_repository.get_by_id(db, existing.user_id) if existing else None
    if user:
        account_lifecycle.ensure_can_log_in(user)

    now = datetime.now(timezone.utc)
    if (
        not existing
        or not user
        or existing.revoked_at is not None
        or existing.expires_at.replace(tzinfo=timezone.utc) < now
    ):
        raise ServiceException(
            status_code=401, title="Unauthorized", detail="Invalid or expired refresh token."
        )

    # Rotate: revoke the used refresh token and issue a new pair for the same device.
    tokens_repository.touch(db, existing, _client_ip(request))
    tokens_repository.revoke(db, existing)

    device = schemas.DeviceInfo(device_id=existing.device_id, device_name=existing.device_name)
    token = _issue_token_pair(db, user, device, request)
    logger.info(f"[AUTH] Refresh token rotado: user_id={user.id}")
    return token


def logout(payload: schemas.LogoutRequest, db: Session) -> dict:
    token_hash = security.hash_token(payload.refresh_token)
    existing = tokens_repository.get_refresh_token_by_hash(db, token_hash)

    if existing and existing.revoked_at is None:
        tokens_repository.revoke(db, existing)
        logger.info(f"[AUTH] Logout: user_id={existing.user_id}")

    return {"message": "Logged out successfully."}


def list_sessions(current_user: models.User, db: Session, current_device_id: str | None = None) -> list[schemas.SessionOut]:
    sessions = tokens_repository.list_active_sessions(db, current_user.id)
    result = []
    for session in sessions:
        out = schemas.SessionOut.model_validate(session)
        out.is_current = bool(current_device_id) and session.device_id == current_device_id
        result.append(out)
    return result


def revoke_session(session_id: UUID, current_user: models.User, db: Session) -> dict:
    session = tokens_repository.get_refresh_token_by_id_for_user(db, session_id, current_user.id)
    if not session:
        raise ServiceException(status_code=404, title="Not Found", detail="Session not found.")

    if session.revoked_at is None:
        tokens_repository.revoke(db, session)

    return {"message": "Session revoked successfully."}


# -------------------------
# Email verification
# -------------------------


def request_email_verification(payload: schemas.EmailVerificationRequest, db: Session) -> dict:
    user = users_repository.get_by_email(db, payload.email)

    if user and not user.email_verified:
        _check_rate_limit(
            db, user.id, VerificationTokenType.EMAIL, "requesting another verification email"
        )
        code = issue_email_verification_code(db, user)
        send_verification_email(to_email=user.email, code=code)
        logger.info(f"[AUTH] Email de verificación reenviado: user_id={user.id}")

    return {
        "message": "If an account exists with that email and is not verified, a new code has been sent."
    }


def confirm_email_verification(payload: schemas.EmailVerificationConfirm, db: Session) -> dict:
    invalid_code_error = ServiceException(
        status_code=400, title="Bad Request", detail="Invalid or expired verification code."
    )

    user = users_repository.get_by_email(db, payload.email)
    if not user:
        raise invalid_code_error

    token = tokens_repository.get_active_verification_token_for_user(
        db, user.id, VerificationTokenType.EMAIL
    )
    if not token:
        raise invalid_code_error

    if token.attempts >= _MAX_VERIFICATION_ATTEMPTS:
        tokens_repository.mark_used(db, token)
        raise ServiceException(
            status_code=400,
            title="Bad Request",
            detail="Too many incorrect attempts. Request a new code.",
        )

    if not secrets.compare_digest(security.hash_token(payload.code), token.token_hash):
        attempts = tokens_repository.increment_attempts(db, token)
        remaining = max(_MAX_VERIFICATION_ATTEMPTS - attempts, 0)
        raise ServiceException(
            status_code=400,
            title="Bad Request",
            detail=f"Invalid verification code. {remaining} attempts remaining.",
        )

    user.email_verified = True
    db.add(user)
    tokens_repository.mark_used(db, token)
    db.commit()

    logger.info(f"[AUTH] Email verificado: user_id={user.id}")
    return {"message": "Email verified successfully. You can now log in."}


# -------------------------
# Password reset
# -------------------------


def request_password_reset(payload: schemas.PasswordResetRequest, db: Session) -> dict:
    user = users_repository.get_by_email(db, payload.email)

    # A user waiting out their deletion may need a new password to log in and reactivate it.
    if user and (account_lifecycle.is_usable(user) or account_lifecycle.can_cancel_deletion(user)):
        _check_rate_limit(
            db, user.id, VerificationTokenType.PASSWORD_RESET, "requesting another password reset"
        )
        tokens_repository.invalidate_active_tokens(db, user.id, VerificationTokenType.PASSWORD_RESET)
        code = security.generate_numeric_code()
        token = models.VerificationToken(
            user_id=user.id,
            type=VerificationTokenType.PASSWORD_RESET,
            token_hash=security.hash_token(code),
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
        )
        tokens_repository.create_verification_token(db, token)
        send_reset_password_email(to_email=user.email, code=code)
        logger.info(f"[AUTH] Código de reset de contraseña enviado: user_id={user.id}")

    return {
        "message": "If an account exists with that email, a password reset email has been sent."
    }


def confirm_password_reset(payload: schemas.PasswordResetConfirm, db: Session) -> dict:
    invalid_code_error = ServiceException(
        status_code=400, title="Bad Request", detail="Invalid or expired reset code."
    )

    user = users_repository.get_by_email(db, payload.email)
    if not user:
        raise invalid_code_error

    token = tokens_repository.get_active_verification_token_for_user(
        db, user.id, VerificationTokenType.PASSWORD_RESET
    )
    if not token:
        raise invalid_code_error

    if token.attempts >= _MAX_VERIFICATION_ATTEMPTS:
        tokens_repository.mark_used(db, token)
        raise ServiceException(
            status_code=400,
            title="Bad Request",
            detail="Too many incorrect attempts. Request a new code.",
        )

    if not secrets.compare_digest(security.hash_token(payload.code), token.token_hash):
        attempts = tokens_repository.increment_attempts(db, token)
        remaining = max(_MAX_VERIFICATION_ATTEMPTS - attempts, 0)
        raise ServiceException(
            status_code=400,
            title="Bad Request",
            detail=f"Invalid reset code. {remaining} attempts remaining.",
        )

    user.password_hash = security.hash_password(payload.new_password)
    db.add(user)
    tokens_repository.mark_used(db, token)
    db.commit()

    # A password reset invalidates every existing session, on every device.
    tokens_repository.revoke_all_for_user(db, user.id)

    logger.info(f"[AUTH] Contraseña reseteada: user_id={user.id}")
    return {
        "message": "Password reset successfully. You can now log in with your new password."
    }


# -------------------------
# Housekeeping (run by the background job in main.py)
# -------------------------

# How long a used-up verification is kept before it's deleted -- a day of margin over any
# code or grace period, for support to look into a signup that just failed.
STALE_VERIFICATION_RETENTION = timedelta(hours=24)


def purge_stale_verifications(db: Session) -> int:
    """Deletes signup verifications (the email/phone people typed in, including signups
    nobody finished) and verification codes that expired more than a day ago."""
    cutoff = datetime.now(timezone.utc) - STALE_VERIFICATION_RETENTION
    return registration_verifications_repository.purge_stale(
        db, cutoff
    ) + tokens_repository.purge_expired_verification_tokens(db, cutoff)
