from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app import models

# -------------------------
# Refresh tokens
# -------------------------


def create_refresh_token(db: Session, refresh_token: models.RefreshToken) -> models.RefreshToken:
    db.add(refresh_token)
    db.flush()
    return refresh_token


def get_refresh_token_by_hash(db: Session, token_hash: str) -> models.RefreshToken | None:
    return (
        db.query(models.RefreshToken)
        .filter(models.RefreshToken.token_hash == token_hash)
        .first()
    )


def get_refresh_token_by_id_for_user(
    db: Session, session_id: UUID, user_id: UUID
) -> models.RefreshToken | None:
    return (
        db.query(models.RefreshToken)
        .filter(
            models.RefreshToken.id == session_id,
            models.RefreshToken.user_id == user_id,
        )
        .first()
    )


def list_active_sessions(db: Session, user_id: UUID) -> list[models.RefreshToken]:
    now = datetime.now(timezone.utc)
    return (
        db.query(models.RefreshToken)
        .filter(
            models.RefreshToken.user_id == user_id,
            models.RefreshToken.revoked_at.is_(None),
            models.RefreshToken.expires_at > now,
        )
        .order_by(func.coalesce(models.RefreshToken.last_used_at, models.RefreshToken.created_at).desc())
        .all()
    )


def revoke(db: Session, refresh_token: models.RefreshToken) -> None:
    refresh_token.revoked_at = datetime.now(timezone.utc)
    db.add(refresh_token)
    db.commit()


def revoke_all_for_user(db: Session, user_id: UUID, except_id: UUID | None = None) -> None:
    now = datetime.now(timezone.utc)
    query = db.query(models.RefreshToken).filter(
        models.RefreshToken.user_id == user_id,
        models.RefreshToken.revoked_at.is_(None),
    )
    if except_id is not None:
        query = query.filter(models.RefreshToken.id != except_id)
    query.update({"revoked_at": now}, synchronize_session=False)
    db.commit()


def touch(db: Session, refresh_token: models.RefreshToken, ip_address: str | None) -> None:
    refresh_token.last_used_at = datetime.now(timezone.utc)
    if ip_address:
        refresh_token.ip_address = ip_address
    db.add(refresh_token)
    db.commit()


# -------------------------
# Verification tokens (email/phone verification, password reset)
# -------------------------


def create_verification_token(
    db: Session, token: models.VerificationToken
) -> models.VerificationToken:
    db.add(token)
    db.commit()
    db.refresh(token)
    return token


def get_valid_verification_token(
    db: Session, token_hash: str, token_type: models.VerificationTokenType
) -> models.VerificationToken | None:
    now = datetime.now(timezone.utc)
    return (
        db.query(models.VerificationToken)
        .filter(
            and_(
                models.VerificationToken.token_hash == token_hash,
                models.VerificationToken.type == token_type,
                models.VerificationToken.used_at.is_(None),
                models.VerificationToken.expires_at > now,
            )
        )
        .first()
    )


def invalidate_active_tokens(
    db: Session, user_id: UUID, token_type: models.VerificationTokenType
) -> None:
    """Marks any unused, unexpired token of this type as used.

    Called before issuing a new token so that only the most recently issued
    one is ever redeemable — otherwise a stale token mailed to a previous
    email address could still be used to "verify" whatever email the user
    has changed to since, without the new address's owner ever seeing it.
    """
    now = datetime.now(timezone.utc)
    db.query(models.VerificationToken).filter(
        models.VerificationToken.user_id == user_id,
        models.VerificationToken.type == token_type,
        models.VerificationToken.used_at.is_(None),
    ).update({"used_at": now}, synchronize_session=False)
    db.commit()


def get_active_verification_token_for_user(
    db: Session, user_id: UUID, token_type: models.VerificationTokenType
) -> models.VerificationToken | None:
    """Latest unused, unexpired token of this type for a specific user.

    Scoping by user (instead of matching the submitted code's hash against
    every active token in the table) keeps the search space for a guessed
    6-digit code limited to this one user's attempts counter.
    """
    now = datetime.now(timezone.utc)
    return (
        db.query(models.VerificationToken)
        .filter(
            and_(
                models.VerificationToken.user_id == user_id,
                models.VerificationToken.type == token_type,
                models.VerificationToken.used_at.is_(None),
                models.VerificationToken.expires_at > now,
            )
        )
        .order_by(models.VerificationToken.created_at.desc())
        .first()
    )


def increment_attempts(db: Session, token: models.VerificationToken) -> int:
    token.attempts += 1
    db.add(token)
    db.commit()
    db.refresh(token)
    return token.attempts


def get_latest_token(
    db: Session, user_id: UUID, token_type: models.VerificationTokenType
) -> models.VerificationToken | None:
    return (
        db.query(models.VerificationToken)
        .filter(
            models.VerificationToken.user_id == user_id,
            models.VerificationToken.type == token_type,
        )
        .order_by(models.VerificationToken.created_at.desc())
        .first()
    )


def mark_used(db: Session, token: models.VerificationToken) -> None:
    token.used_at = datetime.now(timezone.utc)
    db.add(token)
    db.commit()


def purge_expired_verification_tokens(db: Session, older_than: datetime) -> int:
    """Deletes verification codes (email change, password reset...) expired before
    `older_than` -- they can never be used again."""
    deleted = (
        db.query(models.VerificationToken)
        .filter(models.VerificationToken.expires_at < older_than)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted
