import uuid

from sqlalchemy import Column, DateTime, Enum, Index, Integer, String
from sqlalchemy.sql import func

from ..database import Base
from .guid import GUID
from .verification_token import VerificationTokenType


class RegistrationVerification(Base):
    """Email/phone verification that happens BEFORE a user exists yet (the
    signup wizard verifies both channels first, then collects name/birth
    date/password and creates the account already-verified).

    Deliberately separate from `verification_tokens`, which always belongs to
    an existing user (password reset, re-verifying a changed email) -- there's
    no user_id to hang this off yet, so it's keyed by the raw email/phone
    (`target`) instead.
    """

    __tablename__ = "registration_verifications"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    type = Column(Enum(VerificationTokenType, name="verification_token_type"), nullable=False, index=True)
    target = Column(String(255), nullable=False)
    token_hash = Column(String(64), nullable=False, index=True)
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    verified_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_registration_verifications_type_target", "type", "target"),
    )
