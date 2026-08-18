import re
from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, model_validator, StringConstraints
from pydantic_core import PydanticCustomError

from app.models.user import UserStatus

# -------------------------
# HELPERS (internos)
# -------------------------


def _normalize_email(v: str) -> str:
    return v.strip().lower()


def _validate_password_strength(v: str) -> str:
    if len(v) < 8:
        raise PydanticCustomError(
            "password_too_short",
            "Password must be at least 8 characters long",
        )
    if not re.search(r"[A-Z]", v):
        raise PydanticCustomError(
            "password_missing_uppercase",
            "Password must contain at least one uppercase letter",
        )
    if not re.search(r"[a-z]", v):
        raise PydanticCustomError(
            "password_missing_lowercase",
            "Password must contain at least one lowercase letter",
        )
    if not re.search(r"[0-9]", v):
        raise PydanticCustomError(
            "password_missing_number",
            "Password must contain at least one number",
        )
    return v


PhoneStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=6, max_length=30)]


# -------------------------
# AUTH / TOKENS
# -------------------------


class DeviceInfo(BaseModel):
    """Optional device metadata sent by the mobile app to track sessions."""

    device_id: Optional[str] = None
    device_name: Optional[str] = None


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # access token lifetime, in seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class SessionOut(BaseModel):
    id: UUID
    device_id: Optional[str] = None
    device_name: Optional[str] = None
    created_at: datetime
    last_used_at: Optional[datetime] = None
    ip_address: Optional[str] = None
    is_current: bool = False

    model_config = ConfigDict(from_attributes=True)


class UserCreate(DeviceInfo):
    email: EmailStr
    phone: Optional[PhoneStr] = None
    password: str

    @field_validator("email")
    @classmethod
    def email_to_lower(cls, v: EmailStr) -> str:
        return _normalize_email(v)

    @field_validator("password")
    @classmethod
    def password_validator(cls, v: str) -> str:
        return _validate_password_strength(v)


class UserLogin(DeviceInfo):
    email: Optional[EmailStr] = None
    phone: Optional[PhoneStr] = None
    password: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

    @field_validator("email")
    @classmethod
    def email_to_lower(cls, v: Optional[EmailStr]) -> Optional[str]:
        return _normalize_email(v) if v else v

    @model_validator(mode="after")
    def require_identifier(self) -> "UserLogin":
        if not self.email and not self.phone:
            raise PydanticCustomError(
                "missing_identifier", "Either email or phone must be provided"
            )
        return self


class EmailVerificationRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def email_to_lower(cls, v: EmailStr) -> str:
        return _normalize_email(v)


class EmailVerificationConfirm(BaseModel):
    token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def email_to_lower(cls, v: EmailStr) -> str:
        return _normalize_email(v)


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_validator(cls, v: str) -> str:
        return _validate_password_strength(v)


# -------------------------
# USER
# -------------------------


class UserOut(BaseModel):
    id: UUID
    email: EmailStr
    phone: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    avatar_url: Optional[str] = None
    email_verified: bool
    phone_verified: bool
    status: UserStatus
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[PhoneStr] = None
    first_name: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]] = None
    last_name: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]] = None
    avatar_url: Optional[str] = None

    @field_validator("email")
    @classmethod
    def email_to_lower(cls, v: Optional[EmailStr]) -> Optional[str]:
        return _normalize_email(v) if v else v


class AccountDeleteRequest(BaseModel):
    password: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
