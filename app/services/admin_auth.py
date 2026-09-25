from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from loguru import logger
from sqlalchemy.orm import Session

from app import models, schemas, security
from app.config import settings
from app.exceptions.handler import ServiceException
from app.models import AdminRole
from app.repositories import admin_accounts as admin_accounts_repository

# -------------------------
# Login
# -------------------------


def login(username: str, password: str, db: Session) -> schemas.AdminToken:
    admin_account = admin_accounts_repository.get_by_username(db, username)

    if not admin_account or not security.verify_password(password, admin_account.password_hash):
        raise ServiceException(
            status_code=401, title="Unauthorized", detail="Invalid credentials."
        )

    if not admin_account.is_active:
        raise ServiceException(
            status_code=403, title="Forbidden", detail="This admin account has been deactivated."
        )

    admin_account.last_login_at = datetime.now(timezone.utc)
    db.add(admin_account)
    db.commit()

    # `role: admin` is what the gateway's authenticate_admin / every other
    # service's requireAdmin already gate `/admin/*` routes on -- keep that
    # claim name/value exactly as-is. admin_role/admin_username are new,
    # additive, informational claims for the admin frontend.
    access_token = security.create_access_token(
        admin_account.id,
        extra_claims={
            "role": "admin",
            "admin_role": admin_account.role.value,
            "admin_username": admin_account.username,
        },
        expire_minutes=settings.ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES,
    )

    logger.info(f"[ADMIN_AUTH] Login exitoso: admin_id={admin_account.id}")

    return schemas.AdminToken(
        access_token=access_token,
        expires_in=settings.ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# -------------------------
# Superadmin-gated account management
# -------------------------


def _require_active_superadmin(db: Session, admin_id: UUID | None) -> models.AdminAccount:
    admin_account = admin_accounts_repository.get_by_id(db, admin_id) if admin_id else None
    if (
        not admin_account
        or not admin_account.is_active
        or admin_account.role != AdminRole.SUPERADMIN
    ):
        raise ServiceException(
            status_code=403, title="Forbidden", detail="Superadmin privileges required."
        )
    return admin_account


def create_admin_account(
    creator_admin_id: UUID | None, username: str, password: str, role: AdminRole, db: Session
) -> models.AdminAccount:
    _require_active_superadmin(db, creator_admin_id)

    if admin_accounts_repository.get_by_username(db, username):
        raise ServiceException(
            status_code=400, title="Bad Request", detail="Username is already taken."
        )

    admin_account = models.AdminAccount(
        username=username,
        password_hash=security.hash_password(password),
        role=role,
        created_by_admin_id=creator_admin_id,
    )
    admin_accounts_repository.create(db, admin_account)
    db.commit()
    db.refresh(admin_account)

    logger.info(
        f"[ADMIN_AUTH] Cuenta de admin creada: id={admin_account.id}, "
        f"username={admin_account.username}, role={admin_account.role.value}, "
        f"created_by={creator_admin_id}"
    )
    return admin_account


def list_admin_accounts(requester_admin_id: UUID | None, db: Session) -> list[models.AdminAccount]:
    _require_active_superadmin(db, requester_admin_id)
    return admin_accounts_repository.list_all(db)


def set_admin_account_active(
    requester_admin_id: UUID | None, target_id: UUID, is_active: bool, db: Session
) -> models.AdminAccount:
    _require_active_superadmin(db, requester_admin_id)

    if requester_admin_id and target_id == requester_admin_id and not is_active:
        raise ServiceException(
            status_code=400, title="Bad Request", detail="You cannot deactivate your own account."
        )

    target = admin_accounts_repository.get_by_id(db, target_id)
    if not target:
        raise ServiceException(status_code=404, title="Not Found", detail="Admin account not found.")

    admin_accounts_repository.set_active(db, target, is_active)
    logger.info(
        f"[ADMIN_AUTH] Cuenta de admin {'activada' if is_active else 'desactivada'}: "
        f"id={target.id}, by={requester_admin_id}"
    )
    return target
