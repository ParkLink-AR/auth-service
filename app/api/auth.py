from __future__ import annotations
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app import models
from app.api.dependencies import get_current_user
from app.database import get_db
from app.services import auth_service
from app.schemas.schemas import (
    EmailVerificationConfirm,
    EmailVerificationRequest,
    LogoutRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    PhoneRegistrationConfirm,
    PhoneRegistrationRequest,
    RefreshRequest,
    SessionOut,
    Token,
    UserCreate,
    UserLogin,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    return auth_service.register(payload, db)


# -------------------------
# Registration wizard: verify email, then phone, before the account exists
# -------------------------


@router.post("/registration/email/request", response_model=dict)
def request_email_registration(payload: EmailVerificationRequest, db: Session = Depends(get_db)):
    return auth_service.request_email_registration(payload, db)


@router.post("/registration/email/confirm", response_model=dict)
def confirm_email_registration(payload: EmailVerificationConfirm, db: Session = Depends(get_db)):
    return auth_service.confirm_email_registration(payload, db)


@router.post("/registration/phone/request", response_model=dict)
def request_phone_registration(payload: PhoneRegistrationRequest, db: Session = Depends(get_db)):
    return auth_service.request_phone_registration(payload, db)


@router.post("/registration/phone/confirm", response_model=dict)
def confirm_phone_registration(payload: PhoneRegistrationConfirm, db: Session = Depends(get_db)):
    return auth_service.confirm_phone_registration(payload, db)


@router.post("/login", response_model=Token)
def login(payload: UserLogin, request: Request, db: Session = Depends(get_db)):
    return auth_service.login(payload, db, request)


@router.post("/reactivate", response_model=Token)
def reactivate(payload: UserLogin, request: Request, db: Session = Depends(get_db)):
    """Logging in to an account whose deletion is scheduled: cancels the deletion and
    returns a session, with the same credentials as /auth/login."""
    return auth_service.reactivate_and_log_in(payload, db, request)


@router.post("/refresh", response_model=Token)
def refresh(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    return auth_service.refresh(payload, db, request)


@router.post("/logout", response_model=dict)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)):
    return auth_service.logout(payload, db)


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    device_id: str | None = Query(default=None, description="Marks the matching session as current"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List active sessions/devices for the current user."""
    return auth_service.list_sessions(current_user, db, device_id)


@router.delete("/sessions/{session_id}", response_model=dict)
def revoke_session(
    session_id: UUID,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke a specific session (e.g. log out a lost device)."""
    return auth_service.revoke_session(session_id, current_user, db)


@router.post("/email-verification/request", response_model=dict)
def request_email_verification(payload: EmailVerificationRequest, db: Session = Depends(get_db)):
    return auth_service.request_email_verification(payload, db)


@router.post("/email-verification/confirm", response_model=dict)
def confirm_email_verification(payload: EmailVerificationConfirm, db: Session = Depends(get_db)):
    return auth_service.confirm_email_verification(payload, db)


@router.post("/password-reset/request", response_model=dict)
def request_password_reset(payload: PasswordResetRequest, db: Session = Depends(get_db)):
    return auth_service.request_password_reset(payload, db)


@router.post("/password-reset/confirm", response_model=dict)
def confirm_password_reset(payload: PasswordResetConfirm, db: Session = Depends(get_db)):
    return auth_service.confirm_password_reset(payload, db)
