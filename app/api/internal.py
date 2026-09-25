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
    network -- same convention as app/utils/parking_client.py's own calls the
    other direction: no gateway route, no auth header."""
    return schemas.PayoutStatusOut(has_payout_info=users_service.get_payout_status(db, id))
