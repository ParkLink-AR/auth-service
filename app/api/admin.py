from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app import schemas
from app.database import get_db
from app.services import account_lifecycle
from app.services import admin as admin_service

# No in-handler role/auth check here: ParkLink's existing convention (e.g.
# booking-service's /admin/tickets/* handlers) is that the gateway gates
# admin routes on the `role: admin` JWT claim before the request ever
# reaches the service, which trusts it from here on.
router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[schemas.AdminUserSearchOut])
def search_users(
    query: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    return admin_service.search_users(db, query)


@router.get("/users/{id}", response_model=schemas.AdminUserDetailOut)
def get_user_detail(
    id: UUID,
    db: Session = Depends(get_db),
):
    return admin_service.get_user_detail(db, id)


def _admin_id(x_user_id: str | None) -> UUID | None:
    # The gateway sets x-user-id to the admin's own id on ADMIN routes.
    try:
        return UUID(x_user_id) if x_user_id else None
    except ValueError:
        return None


@router.get("/users/{id}/closure-summary", response_model=schemas.AccountClosureSummaryOut)
def get_closure_summary(
    id: UUID,
    db: Session = Depends(get_db),
):
    """What suspending or deleting this account would do, shown before confirming."""
    return account_lifecycle.closure_summary(admin_service.get_user_detail(db, id))


@router.post("/users/{id}/suspend", response_model=schemas.AdminUserDetailOut)
def suspend_user(
    id: UUID,
    payload: schemas.AdminAccountActionRequest,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    return account_lifecycle.suspend(db, id, _admin_id(x_user_id), payload.reason)


@router.post("/users/{id}/reactivate", response_model=schemas.AdminUserDetailOut)
def reactivate_user(
    id: UUID,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    """The only way out of a suspension."""
    return account_lifecycle.reactivate(db, id, _admin_id(x_user_id))


@router.post("/users/{id}/deletion", response_model=schemas.AdminUserDetailOut)
def delete_user_at_holders_request(
    id: UUID,
    payload: schemas.AdminAccountActionRequest,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    """Deletes the account because its holder asked for it outside the app (Ley 25.326,
    art. 16) -- e.g. by email, or a suspended user who can't log in. Wipes the personal
    data right away (unless ParkLink still owes them money, then as soon as it's paid)."""
    return account_lifecycle.admin_request_deletion(db, id, _admin_id(x_user_id), payload.reason)
