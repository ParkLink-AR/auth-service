from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import schemas
from app.database import get_db
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
