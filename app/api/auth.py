from __future__ import annotations
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app import models, schemas, security
from app.api.dependencies import get_current_user
from app.database import get_db
from app.exceptions.handler import ServiceException
from app.models import VerificationTokenType
from app.repositories import tokens as tokens_repository
from app.services import auth_service
from app.utils import html_pages
from app.schemas.schemas import (
    EmailVerificationConfirm,
    EmailVerificationRequest,
    LogoutRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
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


@router.post("/login", response_model=Token)
def login(payload: UserLogin, request: Request, db: Session = Depends(get_db)):
    return auth_service.login(payload, db, request)


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


# -------------------------
# Browser-facing pages linked from emails
# -------------------------


@router.get("/verify-email", response_class=HTMLResponse, include_in_schema=False)
def verify_email_page(token: str, db: Session = Depends(get_db)):
    try:
        auth_service.confirm_email_verification(EmailVerificationConfirm(token=token), db)
    except ServiceException:
        return HTMLResponse(
            html_pages.get_invalid_link_page(
                "Este link de activación venció o ya fue utilizado. Volvé a la app y pedí un nuevo email de verificación."
            ),
            status_code=400,
        )
    return HTMLResponse(html_pages.get_email_verified_page())


@router.get("/reset-password", response_class=HTMLResponse, include_in_schema=False)
def reset_password_page(token: str, db: Session = Depends(get_db)):
    token_hash = security.hash_token(token)
    valid = tokens_repository.get_valid_verification_token(
        db, token_hash, VerificationTokenType.PASSWORD_RESET
    )
    if not valid:
        return HTMLResponse(
            html_pages.get_invalid_link_page(
                "Este link para restablecer tu contraseña venció o ya fue utilizado. Volvé a la app y pedí uno nuevo."
            ),
            status_code=400,
        )
    return HTMLResponse(html_pages.get_reset_password_form_page(token))
