import enum
import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, Enum, String
from sqlalchemy.sql import func

from ..database import Base
from .guid import GUID


class UserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DELETED = "DELETED"


class AccountType(str, enum.Enum):
    DRIVER = "DRIVER"
    OWNER = "OWNER"
    BOTH = "BOTH"


class User(Base):
    __tablename__ = "users"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(30), unique=True, nullable=True, index=True)
    account_type = Column(
        Enum(AccountType, name="account_type"),
        default=AccountType.DRIVER,
        server_default=AccountType.DRIVER.value,
        nullable=False,
    )
    # Set while an email/phone change is awaiting code confirmation; the
    # column above only gets overwritten once the new address/number is
    # actually verified (see users_service.confirm_email_change/confirm_phone_change).
    pending_email = Column(String(255), nullable=True)
    pending_phone = Column(String(30), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    first_name = Column(String(80), nullable=True)
    last_name = Column(String(80), nullable=True)
    dni = Column(String(20), unique=True, nullable=True, index=True)
    birth_date = Column(Date, nullable=True)
    password_hash = Column(String, nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)
    phone_verified = Column(Boolean, default=False, nullable=False)
    status = Column(
        Enum(UserStatus, name="user_status"),
        default=UserStatus.ACTIVE,
        server_default=UserStatus.ACTIVE.value,
        nullable=False,
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    # Manual payout info (parking-spot owners get paid out by hand for now):
    # CBU/CUIL are always digits-only when set, dashes stripped at the schema
    # layer before they ever reach here (see schemas.PayoutInfoUpdate).
    cbu = Column(String(22), nullable=True)
    payout_titular = Column(String(160), nullable=True)
    cuil = Column(String(11), nullable=True)
    payout_info_updated_at = Column(DateTime(timezone=True), nullable=True)
