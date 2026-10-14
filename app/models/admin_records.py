import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from ..database import Base
from .guid import GUID


class PayoutInfoChange(Base):
    """One change to an owner's bank details (CBU, account holder, CUIL), kept so ParkLink
    staff can see where a settlement is going and whether that changed recently -- a CBU
    swapped right before a settlement is the classic way to divert an owner's money."""

    __tablename__ = "payout_info_changes"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    previous_cbu = Column(String(22), nullable=True)
    cbu = Column(String(22), nullable=True)
    previous_titular = Column(String(160), nullable=True)
    titular = Column(String(160), nullable=True)
    previous_cuil = Column(String(11), nullable=True)
    cuil = Column(String(11), nullable=True)
    changed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)


class AdminAuditEntry(Base):
    """Something an admin changed from the panel: who, what (method + path) and how it went.
    Written by the gateway after every successful admin write (see gateway/app/audit.py),
    so every service's admin actions land here without each one logging its own."""

    __tablename__ = "admin_audit_log"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    admin_id = Column(String(64), nullable=True, index=True)
    admin_username = Column(String(64), nullable=True)
    method = Column(String(8), nullable=False)
    path = Column(String(300), nullable=False)
    status_code = Column(Integer, nullable=False)
    # A short summary of the request body (reason/note/status/amount), never secrets.
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
