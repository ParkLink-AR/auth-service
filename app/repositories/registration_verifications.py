from datetime import datetime, timedelta, timezone

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app import models


def create(db: Session, verification: models.RegistrationVerification) -> models.RegistrationVerification:
    db.add(verification)
    db.commit()
    db.refresh(verification)
    return verification


def get_active_for_target(
    db: Session, verification_type: models.VerificationTokenType, target: str
) -> models.RegistrationVerification | None:
    """Latest unused, unexpired (not-yet-verified-or-just-issued) row for this
    email/phone -- used to check the submitted code against."""
    now = datetime.now(timezone.utc)
    return (
        db.query(models.RegistrationVerification)
        .filter(
            and_(
                models.RegistrationVerification.type == verification_type,
                models.RegistrationVerification.target == target,
                models.RegistrationVerification.used_at.is_(None),
                models.RegistrationVerification.expires_at > now,
            )
        )
        .order_by(models.RegistrationVerification.created_at.desc())
        .first()
    )


def get_verified_for_target(
    db: Session, verification_type: models.VerificationTokenType, target: str
) -> models.RegistrationVerification | None:
    """The row `register()` trusts: already verified, not consumed yet, and
    still within the post-verification grace window (`expires_at`, extended
    at verification time) to finish the rest of the signup wizard."""
    now = datetime.now(timezone.utc)
    return (
        db.query(models.RegistrationVerification)
        .filter(
            and_(
                models.RegistrationVerification.type == verification_type,
                models.RegistrationVerification.target == target,
                models.RegistrationVerification.verified_at.isnot(None),
                models.RegistrationVerification.used_at.is_(None),
                models.RegistrationVerification.expires_at > now,
            )
        )
        .order_by(models.RegistrationVerification.created_at.desc())
        .first()
    )


def get_latest_for_target(
    db: Session, verification_type: models.VerificationTokenType, target: str
) -> models.RegistrationVerification | None:
    return (
        db.query(models.RegistrationVerification)
        .filter(
            models.RegistrationVerification.type == verification_type,
            models.RegistrationVerification.target == target,
        )
        .order_by(models.RegistrationVerification.created_at.desc())
        .first()
    )


def increment_attempts(db: Session, verification: models.RegistrationVerification) -> int:
    verification.attempts += 1
    db.add(verification)
    db.commit()
    db.refresh(verification)
    return verification.attempts


def mark_verified(db: Session, verification: models.RegistrationVerification, grace_period: timedelta) -> None:
    verification.verified_at = datetime.now(timezone.utc)
    verification.expires_at = verification.verified_at + grace_period
    db.add(verification)
    db.commit()


def mark_used(db: Session, verification: models.RegistrationVerification) -> None:
    verification.used_at = datetime.now(timezone.utc)
    db.add(verification)
    db.commit()
