import hashlib
import secrets
import string
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


# -------------------------
# Passwords
# -------------------------


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# -------------------------
# Access token (JWT, short-lived)
# -------------------------


def create_access_token(user_id, extra_claims: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    to_encode = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    if extra_claims:
        to_encode.update(extra_claims)
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        return None
    if payload.get("type") != "access":
        return None
    return payload


# -------------------------
# Opaque tokens (refresh tokens, verification/reset tokens)
#
# We never store the raw secret: the raw value is handed to the client
# (or emailed) once, and only its SHA-256 hash lives in the database. This
# lets us revoke/validate tokens without the DB itself being a bearer secret.
# -------------------------


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def generate_numeric_code(length: int = 6) -> str:
    """Short numeric code meant to be typed by hand (e.g. email verification OTP).

    Unlike generate_opaque_token, this is small enough to brute-force if not
    rate-limited -- callers must scope lookups per-user and cap attempts.
    """
    return "".join(secrets.choice(string.digits) for _ in range(length))


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
