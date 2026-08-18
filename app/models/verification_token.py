import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.sql import func

from ..database import Base
from .guid import GUID


class VerificationTokenType(str, enum.Enum):
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    PASSWORD_RESET = "PASSWORD_RESET"


class VerificationToken(Base):
    __tablename__ = "verification_tokens"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type = Column(Enum(VerificationTokenType, name="verification_token_type"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, index=True)
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_verification_tokens_user_type", "user_id", "type"),
    )
