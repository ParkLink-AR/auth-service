from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app import schemas
from app.database import get_db
from app.services import admin_auth as admin_auth_service

router = APIRouter(prefix="/admin", tags=["admin-auth"])


def _parse_admin_id(x_user_id: str | None) -> UUID | None:
    if not x_user_id:
        return None
    try:
        return UUID(x_user_id)
    except ValueError:
        return None


@router.post("/auth/login", response_model=schemas.AdminToken)
def admin_login(payload: schemas.AdminLoginRequest, db: Session = Depends(get_db)):
    """Public endpoint -- no gateway auth gate, this IS the admin login.
    Entirely separate identity system from /auth/login (regular users)."""
    return admin_auth_service.login(payload.username, payload.password, db)


# The endpoints below ARE gated by the gateway on the `role: admin` JWT claim
# like every other /admin/* route, but SUPERADMIN vs ADMIN is a finer
# distinction than that blanket check, so the service layer does its own
# additional superadmin lookup via the caller's id in `X-User-Id` (injected
# by the gateway from the JWT `sub`, same as every other service reads it).


@router.post("/accounts", response_model=schemas.AdminAccountOut, status_code=201)
def create_admin_account(
    payload: schemas.AdminAccountCreate,
    x_user_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    return admin_auth_service.create_admin_account(
        _parse_admin_id(x_user_id), payload.username, payload.password, payload.role, db
    )


@router.get("/accounts", response_model=list[schemas.AdminAccountOut])
def list_admin_accounts(
    x_user_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    return admin_auth_service.list_admin_accounts(_parse_admin_id(x_user_id), db)


@router.get("/accounts/{id}", response_model=schemas.AdminAccountOut)
def get_admin_account(id: UUID, db: Session = Depends(get_db)):
    """Unlike the endpoints above, no superadmin gate -- see
    admin_auth_service.get_admin_account for why."""
    return admin_auth_service.get_admin_account(id, db)


@router.post("/accounts/{id}/password", response_model=schemas.AdminAccountOut)
def set_admin_account_password(
    id: UUID,
    payload: schemas.AdminAccountSetPassword,
    x_user_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    return admin_auth_service.set_admin_account_password(
        _parse_admin_id(x_user_id), id, payload.new_password, db
    )


@router.patch("/accounts/{id}", response_model=schemas.AdminAccountOut)
def set_admin_account_active(
    id: UUID,
    payload: schemas.AdminAccountSetActive,
    x_user_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    return admin_auth_service.set_admin_account_active(
        _parse_admin_id(x_user_id), id, payload.is_active, db
    )
