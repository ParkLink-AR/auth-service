from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app import models, schemas
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


@router.get("/users/{id}/payout-info-history", response_model=list[schemas.PayoutInfoChangeOut])
def get_payout_info_history(
    id: UUID,
    db: Session = Depends(get_db),
):
    """Every change to the owner's bank details, newest first -- shown next to a settlement
    so a CBU swapped right before it stands out."""
    return (
        db.query(models.PayoutInfoChange)
        .filter(models.PayoutInfoChange.user_id == id)
        .order_by(models.PayoutInfoChange.changed_at.desc())
        .limit(50)
        .all()
    )


@router.get("/audit-log", response_model=schemas.AdminAuditPage)
def get_audit_log(
    admin: str | None = Query(default=None, description="Only this admin's actions (username)"),
    query: str | None = Query(default=None, description="Matches the path or the summary"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """What admins did from the panel, newest first (recorded by the gateway)."""
    entries = db.query(models.AdminAuditEntry)
    if admin:
        entries = entries.filter(models.AdminAuditEntry.admin_username == admin)
    if query:
        pattern = f"%{query.strip()}%"
        entries = entries.filter(
            models.AdminAuditEntry.path.ilike(pattern) | models.AdminAuditEntry.summary.ilike(pattern)
        )
    total = entries.count()
    items = entries.order_by(models.AdminAuditEntry.created_at.desc()).offset(offset).limit(limit).all()
    return schemas.AdminAuditPage(items=items, total=total)
