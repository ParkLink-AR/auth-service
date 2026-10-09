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
    # Set while status is PENDING_DELETION: when the data gets wiped. The app shows it in
    # the "your account will be deleted on..." banner, with a button to cancel.
    deletion_scheduled_at: Optional[datetime] = None

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


class PasswordVerifyRequest(BaseModel):
    current_password: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class PasswordChangeRequest(BaseModel):
    current_password: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_validator(cls, v: str) -> str:
        return _validate_password_strength(v)


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
        if not _cbu_check_digits_ok(digits):
            raise PydanticCustomError("invalid_cbu", "CBU check digits don't match -- check for a typo")
        return digits

    @field_validator("cuil")
    @classmethod
    def cuil_validator(cls, v: str) -> str:
        digits = re.sub(r"[-\s]", "", v)
        if not digits.isdigit() or len(digits) != 11:
            raise PydanticCustomError("invalid_cuil", "CUIL must be 11 digits")
        return digits


def _cbu_check_digits_ok(cbu: str) -> bool:
    """A CBU carries two check digits (BCRA's algorithm): the 8th covers the bank+branch
    block, the 22nd the account block. Catches a mistyped digit before ParkLink sends an
    owner's money to the wrong account."""
    digits = [int(c) for c in cbu]
    bank_sum = sum(d * w for d, w in zip(digits[:7], (7, 1, 3, 9, 7, 1, 3)))
    account_sum = sum(d * w for d, w in zip(digits[8:21], (3, 9, 7, 1, 3, 9, 7, 1, 3, 9, 7, 1, 3)))
    return (10 - bank_sum % 10) % 10 == digits[7] and (10 - account_sum % 10) % 10 == digits[21]


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
    # parking-service won't publish a spot for an account that isn't ACTIVE.
    account_status: UserStatus


class AccountStatusOut(BaseModel):
    """Internal: booking-service won't take new bookings from an account that isn't ACTIVE."""

    status: UserStatus


# -------------------------
# ACCOUNT LIFECYCLE (deletion / suspension -- see app/services/account_lifecycle.py)
# -------------------------


class AccountDeletionRequest(BaseModel):
    password: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class AdminAccountActionRequest(BaseModel):
    """Why an admin suspends an account or deletes it at the holder's request -- kept on
    the account, for the record."""

    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class AccountClosureSummaryOut(BaseModel):
    """What closing (or suspending) the account would do, shown before confirming."""

    blocked: bool
    blocked_reason: Optional[str] = None
    in_progress_count: int
    driver_bookings_to_cancel: int
    owner_bookings_to_cancel: int
    owner_requests_to_reject: int
    pending_payout_count: int
    pending_payout_amount: int  # centavos
    spot_count: int
    deletion_date: datetime


# -------------------------
# VEHICLES (a driver's own cars -- entirely optional, picked when booking a spot so the
# owner knows which plate to expect)
# -------------------------


VehiclePlateStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10)]
VehicleBrandStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
VehicleModelStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]

# Argentina only, for now -- the plate graphic (mobile's VehiclePlate.tsx) is a faithful
# recreation of a real Argentine plate, and doing the same for every other country isn't
# worth it yet. A set (not a single constant) so this is just one line to widen later.
VEHICLE_COUNTRIES = {"AR"}

# The kinds of vehicle -- the same values a parking spot accepts (parking-service's
# VehicleType): a vehicle fits a spot that lists its type, and a spot priced per vehicle
# type charges by it.
VEHICLE_TYPES = {"car", "suv", "pickup", "van", "motorcycle", "bicycle"}
BICYCLE = "bicycle"


# Argentina only ever issued four domain formats -- two for cars, two for motorcycles (one
# digit/letter shorter on one side than the car's equivalent era): three letters + three
# digits (pre-2016 car, e.g. ABC123) / three digits + three letters (pre-2016 moto, e.g.
# 123ABC), and the current Mercosur ones, two letters + three digits + two letters (car,
# e.g. AB123CD) / one letter + three digits + three letters (moto, e.g. A123ABC). A plate
# matching none of these four is not a valid Argentine domain -- see mobile's
# VehiclePlate.tsx, which mirrors this exact set of patterns to also pick which plate
# graphic to draw.
AR_CAR_OLD_PLATE_FORMAT = re.compile(r"^[A-Z]{3}\d{3}$")
AR_CAR_MERCOSUR_PLATE_FORMAT = re.compile(r"^[A-Z]{2}\d{3}[A-Z]{2}$")
AR_MOTO_OLD_PLATE_FORMAT = re.compile(r"^\d{3}[A-Z]{3}$")
AR_MOTO_MERCOSUR_PLATE_FORMAT = re.compile(r"^[A-Z]\d{3}[A-Z]{3}$")


def _capitalize_words(text: str) -> str:
    """First letter of every word uppercase, the rest left as typed -- "honda xr 250" ->
    "Honda Xr 250", while "BMW" or "XR 250" stay as they are. Extra spaces collapse."""
    return " ".join(word[:1].upper() + word[1:] for word in text.split())


class VehicleCreate(BaseModel):
    type: str
    # A bicycle has no plate, and its brand/model are optional; every other type needs all
    # three (see required_fields_validator).
    plate: VehiclePlateStr | None = None
    brand: VehicleBrandStr | None = None
    model: VehicleModelStr | None = None
    country: str

    @field_validator("type")
    @classmethod
    def type_validator(cls, v: str) -> str:
        vehicle_type = v.strip().lower()
        if vehicle_type not in VEHICLE_TYPES:
            raise PydanticCustomError("invalid_vehicle_type", "Unsupported vehicle type")
        return vehicle_type

    @field_validator("plate")
    @classmethod
    def plate_validator(cls, v: str | None) -> str | None:
        # Stored the way it's printed on the plate: uppercase, no spaces or dashes
        # ("ab 123-cd" -> "AB123CD").
        return None if v is None else re.sub(r"[\s\-.]", "", v).upper()

    @field_validator("brand", "model")
    @classmethod
    def name_validator(cls, v: str | None) -> str | None:
        return None if v is None else _capitalize_words(v)

    @field_validator("country")
    @classmethod
    def country_validator(cls, v: str) -> str:
        code = v.strip().upper()
        if code not in VEHICLE_COUNTRIES:
            raise PydanticCustomError("invalid_country", "Unsupported vehicle country")
        return code

    @model_validator(mode="after")
    def required_fields_validator(self) -> "VehicleCreate":
        if self.type == BICYCLE:
            # Nothing to identify it by but its description: a plate sent anyway is dropped.
            self.plate = None
            return self
        missing = [name for name in ("plate", "brand", "model") if not getattr(self, name)]
        if missing:
            raise PydanticCustomError(
                "vehicle_fields_required",
                "Plate, brand and model are required for every vehicle but a bicycle",
            )
        return self

    @model_validator(mode="after")
    def ar_plate_format_validator(self) -> "VehicleCreate":
        if self.plate is not None and self.country == "AR" and not (
            AR_CAR_OLD_PLATE_FORMAT.match(self.plate)
            or AR_CAR_MERCOSUR_PLATE_FORMAT.match(self.plate)
            or AR_MOTO_OLD_PLATE_FORMAT.match(self.plate)
            or AR_MOTO_MERCOSUR_PLATE_FORMAT.match(self.plate)
        ):
            raise PydanticCustomError(
                "invalid_ar_plate",
                "An Argentine plate must be one of: ABC123/AB123CD (car) or 123ABC/A123ABC (motorcycle)",
            )
        return self


class VehicleTypeUpdate(BaseModel):
    """Fills in the type of a vehicle saved before vehicles had one."""

    type: str

    @field_validator("type")
    @classmethod
    def type_validator(cls, v: str) -> str:
        vehicle_type = v.strip().lower()
        if vehicle_type not in VEHICLE_TYPES or vehicle_type == BICYCLE:
            # A vehicle saved before types existed always has a plate -- it's not a bicycle.
            raise PydanticCustomError("invalid_vehicle_type", "Unsupported vehicle type")
        return vehicle_type


class VehicleOut(BaseModel):
    id: UUID
    # null only for a vehicle saved before types existed.
    type: str | None
    plate: str | None
    brand: str | None
    model: str | None
    country: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


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
    dni: Optional[str] = None
    account_type: AccountType
    status: UserStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminUserDetailOut(AdminUserSearchOut):
    avatar_url: Optional[str] = None
    cbu: Optional[str] = None
    payout_titular: Optional[str] = None
    cuil: Optional[str] = None
    email_verified: bool
    phone_verified: bool
    last_login_at: Optional[datetime] = None
    suspended_at: Optional[datetime] = None
    suspended_by_admin_id: Optional[UUID] = None
    suspension_reason: Optional[str] = None
    deletion_requested_at: Optional[datetime] = None
    deletion_scheduled_at: Optional[datetime] = None
    deletion_requested_by_admin_id: Optional[UUID] = None
    deletion_reason: Optional[str] = None
    deleted_at: Optional[datetime] = None

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
