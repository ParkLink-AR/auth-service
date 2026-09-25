import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum, String
from sqlalchemy.sql import func

from ..database import Base
from .guid import GUID


class AdminRole(str, enum.Enum):
    SUPERADMIN = "SUPERADMIN"
    ADMIN = "ADMIN"


class AdminAccount(Base):
    """ParkLink staff/admin identity -- deliberately unrelated to the `users`
    table (no FK, no shared login flow): admin accounts are their own
    username+password identity system, managed by a superadmin from inside
    the admin panel. See app/services/admin_auth.py."""

    __tablename__ = "admin_accounts"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    username = Column(String(60), unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(
        Enum(AdminRole, name="admin_role"),
        nullable=False,
        default=AdminRole.ADMIN,
        server_default=AdminRole.ADMIN.value,
    )
    is_active = Column(Boolean, default=True, nullable=False, server_default="true")
    created_by_admin_id = Column(GUID(), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_login_at = Column(DateTime(timezone=True), nullable=True)
