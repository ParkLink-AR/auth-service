from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
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
