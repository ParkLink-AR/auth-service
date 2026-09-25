import re
from datetime import date, datetime
from typing import Annotated, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, computed_field, field_validator, model_validator, StringConstraints
from pydantic_core import PydanticCustomError

from app.models.admin_account import AdminRole
from app.models.user import UserStatus, AccountType

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

# E.164 (+549..., +1..., etc). Used where the phone is a verified channel
# (signup wizard), stricter than the generic PhoneStr above.
PhoneE164Str = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\+\d{8,15}$")]

MIN_SIGNUP_AGE_YEARS = 18


def _validate_min_age(v: date) -> date:
    today = date.today()
    age = today.year - v.year - ((today.month, today.day) < (v.month, v.day))
    if age < MIN_SIGNUP_AGE_YEARS:
        raise PydanticCustomError(
            "underage", f"You must be at least {MIN_SIGNUP_AGE_YEARS} years old"
        )
    return v


# Argentine DNI: digits only once dots/spaces are stripped ("12.345.678" or
# "12345678"), 7-8 digits.
DniStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=7, max_length=10)]


def _normalize_dni(v: str) -> str:
    digits = re.sub(r"[.\s]", "", v)
    if not digits.isdigit() or not (7 <= len(digits) <= 8):
        raise PydanticCustomError("invalid_dni", "DNI must be 7-8 digits")
    return digits


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


NameStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class UserCreate(DeviceInfo):
    email: EmailStr
    phone: PhoneE164Str
    first_name: NameStr
    last_name: NameStr
    dni: DniStr
    birth_date: date
    password: str
    account_type: AccountType = AccountType.DRIVER

    @field_validator("email")
    @classmethod
    def email_to_lower(cls, v: EmailStr) -> str:
        return _normalize_email(v)

    @field_validator("dni")
    @classmethod
    def dni_validator(cls, v: str) -> str:
        return _normalize_dni(v)

    @field_validator("birth_date")
    @classmethod
    def birth_date_validator(cls, v: date) -> date:
        return _validate_min_age(v)

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
    email: EmailStr
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=6, max_length=6)]

    @field_validator("email")
    @classmethod
    def email_to_lower(cls, v: EmailStr) -> str:
        return _normalize_email(v)

    @field_validator("code")
    @classmethod
    def code_is_digits(cls, v: str) -> str:
        if not v.isdigit():
            raise PydanticCustomError("invalid_code", "Code must be 6 digits")
        return v


class PhoneRegistrationRequest(BaseModel):
    phone: PhoneE164Str


class PhoneRegistrationConfirm(BaseModel):
    phone: PhoneE164Str
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=6, max_length=6)]

    @field_validator("code")
    @classmethod
    def code_is_digits(cls, v: str) -> str:
        if not v.isdigit():
            raise PydanticCustomError("invalid_code", "Code must be 6 digits")
        return v


class EmailChangeRequest(BaseModel):
    new_email: EmailStr

    @field_validator("new_email")
    @classmethod
    def email_to_lower(cls, v: EmailStr) -> str:
        return _normalize_email(v)


class EmailChangeConfirm(BaseModel):
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=6, max_length=6)]

    @field_validator("code")
    @classmethod
    def code_is_digits(cls, v: str) -> str:
        if not v.isdigit():
            raise PydanticCustomError("invalid_code", "Code must be 6 digits")
        return v


class PhoneChangeRequest(BaseModel):
    new_phone: PhoneE164Str


class PhoneChangeConfirm(BaseModel):
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=6, max_length=6)]

    @field_validator("code")
    @classmethod
    def code_is_digits(cls, v: str) -> str:
        if not v.isdigit():
            raise PydanticCustomError("invalid_code", "Code must be 6 digits")
        return v


class PasswordResetRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def email_to_lower(cls, v: EmailStr) -> str:
        return _normalize_email(v)


class PasswordResetConfirm(BaseModel):
    email: EmailStr
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=6, max_length=6)]
    new_password: str

    @field_validator("email")
    @classmethod
    def email_to_lower(cls, v: EmailStr) -> str:
        return _normalize_email(v)

    @field_validator("code")
    @classmethod
    def code_is_digits(cls, v: str) -> str:
        if not v.isdigit():
            raise PydanticCustomError("invalid_code", "Code must be 6 digits")
        return v

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
    dni: Optional[str] = None
    avatar_url: Optional[str] = None
    birth_date: Optional[date] = None
    email_verified: bool
    phone_verified: bool
    status: UserStatus
    account_type: AccountType = AccountType.DRIVER
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def name(self) -> str:
        """Full display name -- kept as a single computed field so mobile
        (and anything else consuming this API) doesn't need to know the
        identity is stored as first_name/last_name under the hood."""
        return f"{self.first_name or ''} {self.last_name or ''}".strip()


class PublicUserOut(BaseModel):
    """What any authenticated user can see about another one -- e.g. a driver
    checking who owns a spot, or an owner checking who's requesting a
    booking. Deliberately excludes email/phone/dni: those stay private to
    the account owner (see UserOut, which _require_self still guards)."""

    id: UUID
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def name(self) -> str:
        return f"{self.first_name or ''} {self.last_name or ''}".strip()


class UserUpdate(BaseModel):
    """Profile fields editable in one shot. Email and phone are deliberately
    excluded -- each has its own request/confirm endpoints (see
    EmailChangeRequest/PhoneChangeRequest) since changing either requires
    verifying the new value before it takes effect."""

    first_name: Optional[NameStr] = None
    last_name: Optional[NameStr] = None
    account_type: Optional[AccountType] = None


class AccountDeleteRequest(BaseModel):
    password: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


# -------------------------
# PAYOUT INFO (manual payouts to parking-spot owners: CBU + titular + CUIL)
# -------------------------


PayoutTitularStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]


class PayoutInfoUpdate(BaseModel):
    cbu: str
    payout_titular: PayoutTitularStr
    cuil: str

    @field_validator("cbu")
    @classmethod
    def cbu_validator(cls, v: str) -> str:
        digits = v.strip()
        if not digits.isdigit() or len(digits) != 22:
            raise PydanticCustomError("invalid_cbu", "CBU must be exactly 22 digits")
        return digits

    @field_validator("cuil")
    @classmethod
    def cuil_validator(cls, v: str) -> str:
        digits = re.sub(r"[-\s]", "", v)
        if not digits.isdigit() or len(digits) != 11:
            raise PydanticCustomError("invalid_cuil", "CUIL must be 11 digits")
        return digits


class PayoutInfoOut(BaseModel):
    cbu: Optional[str] = None
    payout_titular: Optional[str] = None
    cuil: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def has_payout_info(self) -> bool:
        return bool(self.cbu and self.payout_titular and self.cuil)


class PayoutStatusOut(BaseModel):
    """Internal (service-to-service) shape -- see app/api/internal.py."""

    has_payout_info: bool


# -------------------------
# ADMIN (ParkLink staff -- gateway gates these routes on the `role: admin`
# JWT claim before the request ever reaches this service; see
# admin_auth_service.login and app/api/admin.py)
# -------------------------


class AdminUserSearchOut(BaseModel):
    id: UUID
    email: EmailStr
    phone: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    account_type: AccountType
    status: UserStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminUserDetailOut(AdminUserSearchOut):
    dni: Optional[str] = None
    avatar_url: Optional[str] = None
    cbu: Optional[str] = None
    payout_titular: Optional[str] = None
    cuil: Optional[str] = None
    email_verified: bool
    phone_verified: bool
    last_login_at: Optional[datetime] = None

    @computed_field
    @property
    def has_payout_info(self) -> bool:
        return bool(self.cbu and self.payout_titular and self.cuil)


# -------------------------
# ADMIN AUTH (separate identity system for ParkLink staff/admin accounts --
# entirely unrelated to the `users` table above; see app/services/
# admin_auth.py and app/api/admin_auth.py)
# -------------------------


class AdminLoginRequest(BaseModel):
    username: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
    password: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class AdminToken(BaseModel):
    """Admin sessions don't get a refresh token -- just a longer-lived access
    token (see ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES); the admin frontend simply
    re-logs-in when it expires."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # access token lifetime, in seconds


class AdminAccountCreate(BaseModel):
    username: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
    password: str
    role: AdminRole = AdminRole.ADMIN

    @field_validator("password")
    @classmethod
    def password_validator(cls, v: str) -> str:
        return _validate_password_strength(v)


class AdminAccountSetActive(BaseModel):
    is_active: bool


class AdminAccountSetPassword(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def new_password_validator(cls, v: str) -> str:
        return _validate_password_strength(v)


class AdminAccountOut(BaseModel):
    id: UUID
    username: str
    role: AdminRole
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
