from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services import users as users_service

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/users/{id}/payout-status", response_model=schemas.PayoutStatusOut)
def get_payout_status(
    id: UUID,
    db: Session = Depends(get_db),
):
    """Called service-to-service by parking-service, direct on the docker
    network -- no gateway route; app/trusted_caller.py only lets it through
    with the shared INTERNAL_SERVICE_KEY."""
    return users_service.get_payout_status(db, id)


@router.get("/users/{id}/account-status", response_model=schemas.AccountStatusOut)
def get_account_status(
    id: UUID,
    db: Session = Depends(get_db),
):
    """Called by booking-service before taking a new booking: only an ACTIVE account can
    book (not a suspended one, nor one being deleted)."""
    return users_service.get_account_status(db, id)


@router.post("/admin-audit", status_code=204)
def record_admin_action(
    payload: schemas.AdminAuditCreate,
    db: Session = Depends(get_db),
):
    """Called by the gateway after every admin write it proxied (see gateway/app/audit.py)."""
    db.add(models.AdminAuditEntry(**payload.model_dump()))
    db.commit()


_AUDIENCE_ACCOUNT_TYPES = {
    "drivers": (models.AccountType.DRIVER, models.AccountType.BOTH),
    "owners": (models.AccountType.OWNER, models.AccountType.BOTH),
}


@router.get("/users/ids", response_model=list[UUID])
def list_user_ids(
    audience: str = Query(default="all", pattern="^(all|drivers|owners)$"),
    db: Session = Depends(get_db),
):
    """Every active account in an audience -- for notifications-service to send an admin's
    announcement (see its /admin/broadcasts)."""
    users = db.query(models.User.id).filter(models.User.status == models.UserStatus.ACTIVE)
    if audience in _AUDIENCE_ACCOUNT_TYPES:
        users = users.filter(models.User.account_type.in_(_AUDIENCE_ACCOUNT_TYPES[audience]))
    return [row.id for row in users.all()]
