from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Request
from loguru import logger
from sqlalchemy.orm import Session

from app import models, schemas, security
from app.config import settings
from app.exceptions.handler import ServiceException
from app.models import UserStatus, VerificationTokenType
from app.repositories import tokens as tokens_repository
from app.repositories import users as users_repository
from app.utils.email import send_reset_password_email, send_verification_email

_RATE_LIMIT_SECONDS = 60


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


def _issue_verification_token(
    db: Session, user: models.User, token_type: VerificationTokenType, expires_delta: timedelta
) -> str:
    tokens_repository.invalidate_active_tokens(db, user.id, token_type)
    raw_token = security.generate_opaque_token()
    token = models.VerificationToken(
        user_id=user.id,
        type=token_type,
        token_hash=security.hash_token(raw_token),
        expires_at=datetime.now(timezone.utc) + expires_delta,
    )
    tokens_repository.create_verification_token(db, token)
    return raw_token


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
# Register
# -------------------------


def register(payload: schemas.UserCreate, db: Session) -> models.User:
    logger.debug(f"[AUTH] Intento de registro: email={payload.email}")

    if users_repository.get_by_email(db, payload.email):
        raise ServiceException(
            status_code=400, title="Bad Request", detail="Email is already registered."
        )

    if payload.phone and users_repository.get_by_phone(db, payload.phone):
        raise ServiceException(
            status_code=400, title="Bad Request", detail="Phone is already registered."
        )

    user = models.User(
        email=payload.email,
        phone=payload.phone,
        password_hash=security.hash_password(payload.password),
        email_verified=settings.SKIP_EMAIL_VERIFICATION,
    )

    try:
        users_repository.create(db, user)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(user)

    if not settings.SKIP_EMAIL_VERIFICATION:
        raw_token = _issue_verification_token(
            db,
            user,
            VerificationTokenType.EMAIL,
            timedelta(hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS),
        )
        send_verification_email(to_email=user.email, verification_token=raw_token)

    logger.info(f"[AUTH] Usuario registrado: id={user.id}, email={user.email}")
    return user


# -------------------------
# Login / refresh / logout
# -------------------------


def login(payload: schemas.UserLogin, db: Session, request: Request | None = None) -> schemas.Token:
    logger.debug(f"[AUTH] Intento de login: email={payload.email}, phone={payload.phone}")

    user = users_repository.get_by_email(db, payload.email) if payload.email else None
    if user is None and payload.phone:
        user = users_repository.get_by_phone(db, payload.phone)

    if not user or not security.verify_password(payload.password, user.password_hash):
        raise ServiceException(
            status_code=401, title="Unauthorized", detail="Invalid credentials."
        )

    if user.status == UserStatus.DELETED:
        raise ServiceException(
            status_code=401, title="Unauthorized", detail="Invalid credentials."
        )

    if user.status == UserStatus.SUSPENDED:
        raise ServiceException(
            status_code=403, title="Forbidden", detail="Your account has been suspended."
        )

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

    now = datetime.now(timezone.utc)
    if (
        not existing
        or existing.revoked_at is not None
        or existing.expires_at.replace(tzinfo=timezone.utc) < now
    ):
        raise ServiceException(
            status_code=401, title="Unauthorized", detail="Invalid or expired refresh token."
        )

    user = users_repository.get_by_id(db, existing.user_id)
    if not user or user.status != UserStatus.ACTIVE:
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
        raw_token = _issue_verification_token(
            db,
            user,
            VerificationTokenType.EMAIL,
            timedelta(hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS),
        )
        send_verification_email(to_email=user.email, verification_token=raw_token)
        logger.info(f"[AUTH] Email de verificación reenviado: user_id={user.id}")

    return {
        "message": "If an account exists with that email and is not verified, a new code has been sent."
    }


def confirm_email_verification(payload: schemas.EmailVerificationConfirm, db: Session) -> dict:
    token_hash = security.hash_token(payload.token)
    token = tokens_repository.get_valid_verification_token(db, token_hash, VerificationTokenType.EMAIL)

    if not token:
        raise ServiceException(
            status_code=400, title="Bad Request", detail="Invalid or expired verification code."
        )

    user = users_repository.get_by_id(db, token.user_id)
    if not user:
        raise ServiceException(status_code=404, title="Not Found", detail="User not found.")

    user.email_verified = True
    db.add(user)
    tokens_repository.mark_used(db, token)

    logger.info(f"[AUTH] Email verificado: user_id={user.id}")
    return {"message": "Email verified successfully. You can now log in."}


# -------------------------
# Password reset
# -------------------------


def request_password_reset(payload: schemas.PasswordResetRequest, db: Session) -> dict:
    user = users_repository.get_by_email(db, payload.email)

    if user and user.status == UserStatus.ACTIVE:
        _check_rate_limit(
            db, user.id, VerificationTokenType.PASSWORD_RESET, "requesting another password reset"
        )
        raw_token = _issue_verification_token(
            db,
            user,
            VerificationTokenType.PASSWORD_RESET,
            timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
        )
        send_reset_password_email(to_email=user.email, reset_token=raw_token)
        logger.info(f"[AUTH] Email de reset de contraseña enviado: user_id={user.id}")

    return {
        "message": "If an account exists with that email, a password reset email has been sent."
    }


def confirm_password_reset(payload: schemas.PasswordResetConfirm, db: Session) -> dict:
    token_hash = security.hash_token(payload.token)
    token = tokens_repository.get_valid_verification_token(
        db, token_hash, VerificationTokenType.PASSWORD_RESET
    )

    if not token:
        raise ServiceException(
            status_code=400, title="Bad Request", detail="Invalid or expired reset code."
        )

    user = users_repository.get_by_id(db, token.user_id)
    if not user:
        raise ServiceException(status_code=404, title="Not Found", detail="User not found.")

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
