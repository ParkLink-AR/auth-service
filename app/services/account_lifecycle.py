"""Account lifecycle: deletion (asked for by the user, or by an admin at the holder's
request), suspension and reactivation.

    ACTIVE --(user asks)------------> PENDING_DELETION --(grace period over)--> DELETED
    ACTIVE --(admin, holder's request)-> PENDING_DELETION (due now) ----------> DELETED
    PENDING_DELETION --(user reactivates it when logging in, only if they asked for it)--> ACTIVE
    ACTIVE / PENDING_DELETION --(admin suspends)--> SUSPENDED --(admin reactivates)--> ACTIVE

Closing or suspending an account has the same effects on the rest of the platform: the
owner's spots stop showing up in search, every booking that hasn't started yet is cancelled
with a full refund, push tokens are dropped and every session is closed. A booking in
progress (the car is parked right now) blocks it until it ends.

Deleting never drops the row: the personal data is wiped (anonymized) and the row stays, so
the bookings, payments and reviews the other services keep pointing at something -- the
records the law requires keeping remain, without anything that identifies the person (Ley
25.326, art. 2 "disociación" and art. 16). The wipe waits until ParkLink has paid the owner
everything it owes them, since that needs their payout details.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy.orm import Session

from app import models, schemas, security
from app.config import settings
from app.exceptions.handler import ServiceException
from app.models import UserStatus
from app.repositories import tokens as tokens_repository
from app.utils import booking_client, notifications_client, parking_client
from app.utils.avatar import delete_avatar_file
from app.utils.email import (
    send_account_deleted_email,
    send_account_deletion_cancelled_email,
    send_account_deletion_scheduled_email,
    send_account_reactivated_email,
    send_account_suspended_email,
)

ARGENTINA_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
DELETED_NAME = ("Usuario", "eliminado")
# A real, ParkLink-owned domain (email validation rejects reserved ones like .invalid);
# nothing is ever sent to it, a DELETED account can't log in or get mail.
DELETED_EMAIL_DOMAIN = "usuarios-eliminados.parklink.com.ar"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    # SQLite (tests) hands timestamps back naive.
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def format_date(value: datetime) -> str:
    return _as_utc(value).astimezone(ARGENTINA_TZ).strftime("%d/%m/%Y")


def can_cancel_deletion(user: models.User) -> bool:
    """Only a deletion the user asked for themselves, still within its grace period."""
    return (
        user.status == UserStatus.PENDING_DELETION
        and user.deletion_requested_by_admin_id is None
        and user.deletion_scheduled_at is not None
        and _as_utc(user.deletion_scheduled_at) > _now()
    )


def is_usable(user: models.User) -> bool:
    """Whether the user can have a session at all: only an active account. One waiting out
    a deletion has to reactivate it first (see reactivate_and_log_in in auth_service)."""
    return user.status == UserStatus.ACTIVE


def ensure_can_log_in(user: models.User) -> None:
    """Raises the error a user who isn't usable gets when logging in."""
    if is_usable(user):
        return
    if can_cancel_deletion(user):
        # The app answers this one with "reactivate your account?" -- see /auth/reactivate.
        raise ServiceException(
            status_code=403,
            title="Forbidden",
            detail=f"Tu cuenta se va a eliminar el {format_date(user.deletion_scheduled_at)}.",
            code="ACCOUNT_DELETION_SCHEDULED",
            extra={"deletion_scheduled_at": _as_utc(user.deletion_scheduled_at).isoformat()},
        )
    if user.status == UserStatus.SUSPENDED:
        raise ServiceException(
            status_code=403,
            title="Forbidden",
            detail=(
                "Tu cuenta está suspendida. Para regularizarla, escribinos a "
                f"{settings.SUPPORT_EMAIL}."
            ),
            code="ACCOUNT_SUSPENDED",
        )
    if user.status == UserStatus.PENDING_DELETION:
        raise ServiceException(
            status_code=403,
            title="Forbidden",
            detail=(
                "Tu cuenta se está eliminando. Si es un error, escribinos a "
                f"{settings.SUPPORT_EMAIL}."
            ),
            code="ACCOUNT_DELETION_IN_PROGRESS",
        )
    raise ServiceException(status_code=401, title="Unauthorized", detail="Invalid credentials.")


def ensure_identifier_available(user: models.User | None, field_detail: str) -> None:
    """For registration: an email/phone/DNI still held by an account that's being deleted
    gets its own message instead of a plain "already registered"."""
    if user is None:
        return
    if user.status == UserStatus.PENDING_DELETION:
        raise ServiceException(
            status_code=400,
            title="Bad Request",
            detail=(
                "Ya hay una cuenta con estos datos que se está eliminando. Iniciá sesión para "
                "cancelar la eliminación, o esperá a que termine para registrarte de nuevo."
            ),
            code="ACCOUNT_PENDING_DELETION",
        )
    raise ServiceException(status_code=400, title="Bad Request", detail=field_detail)


# -------------------------
# Summary (what closing the account would do)
# -------------------------


def closure_summary(user: models.User) -> schemas.AccountClosureSummaryOut:
    spot_ids = parking_client.list_owner_spot_ids(user.id)
    raw = booking_client.get_account_closure_summary(user.id, spot_ids)
    in_progress = int(raw.get("in_progress_count", 0))
    return schemas.AccountClosureSummaryOut(
        blocked=in_progress > 0,
        blocked_reason=(
            "Tenés una reserva en curso. Vas a poder eliminar la cuenta cuando termine."
            if in_progress > 0
            else None
        ),
        in_progress_count=in_progress,
        driver_bookings_to_cancel=int(raw.get("driver_bookings_to_cancel", 0)),
        owner_bookings_to_cancel=int(raw.get("owner_bookings_to_cancel", 0)),
        owner_requests_to_reject=int(raw.get("owner_requests_to_reject", 0)),
        pending_payout_count=int(raw.get("pending_payout_count", 0)),
        pending_payout_amount=int(raw.get("pending_payout_amount", 0)),
        spot_count=len(spot_ids),
        deletion_date=_now() + timedelta(days=settings.ACCOUNT_DELETION_GRACE_DAYS),
    )


def _ensure_not_blocked(summary: schemas.AccountClosureSummaryOut, blocked_detail: str) -> None:
    if summary.blocked:
        raise ServiceException(
            status_code=409, title="Conflict", detail=blocked_detail, code="ACCOUNT_HAS_BOOKING_IN_PROGRESS"
        )


def _close_down(db: Session, user: models.User) -> None:
    """What suspending and closing an account share: spots out of search, upcoming
    bookings cancelled and refunded, no more pushes, every session closed. Every step is
    idempotent, so a failure halfway can simply be retried."""
    spot_ids = parking_client.pause_owner_spots(user.id)
    booking_client.cancel_account_bookings(user.id, spot_ids)
    notifications_client.delete_device_tokens(user.id)
    tokens_repository.revoke_all_for_user(db, user.id)


# -------------------------
# Deletion asked for by the user (from the app)
# -------------------------


def request_deletion(db: Session, user: models.User, password: str) -> models.User:
    if not security.verify_password(password, user.password_hash):
        raise ServiceException(status_code=401, title="Unauthorized", detail="Contraseña incorrecta.")
    if user.status != UserStatus.ACTIVE:
        raise ServiceException(
            status_code=409, title="Conflict", detail="Tu cuenta ya se está eliminando.", code="ACCOUNT_NOT_ACTIVE"
        )

    summary = closure_summary(user)
    _ensure_not_blocked(summary, summary.blocked_reason or "")

    _close_down(db, user)

    now = _now()
    user.status = UserStatus.PENDING_DELETION
    user.deletion_requested_at = now
    user.deletion_scheduled_at = now + timedelta(days=settings.ACCOUNT_DELETION_GRACE_DAYS)
    user.deletion_requested_by_admin_id = None
    user.deletion_reason = None
    db.add(user)
    db.commit()
    db.refresh(user)

    send_account_deletion_scheduled_email(user.email, format_date(user.deletion_scheduled_at), can_cancel=True)
    logger.info(f"[ACCOUNT] Eliminación programada por el usuario: user_id={user.id} para {user.deletion_scheduled_at}")
    return user


def cancel_deletion(db: Session, user: models.User) -> models.User:
    if not can_cancel_deletion(user):
        raise ServiceException(
            status_code=409,
            title="Conflict",
            detail="Tu cuenta no tiene una eliminación pendiente que puedas cancelar.",
            code="NO_CANCELLABLE_DELETION",
        )

    parking_client.restore_owner_spots(user.id)

    user.status = UserStatus.ACTIVE
    user.deletion_requested_at = None
    user.deletion_scheduled_at = None
    db.add(user)
    db.commit()
    db.refresh(user)

    send_account_deletion_cancelled_email(user.email)
    logger.info(f"[ACCOUNT] Eliminación cancelada por el usuario: user_id={user.id}")
    return user


# -------------------------
# Admin actions
# -------------------------


def _get_user(db: Session, user_id: UUID) -> models.User:
    user = db.get(models.User, user_id)
    if not user or user.status == UserStatus.DELETED:
        raise ServiceException(status_code=404, title="Not Found", detail="Usuario no encontrado.")
    return user


def suspend(db: Session, user_id: UUID, admin_id: UUID | None, reason: str) -> models.User:
    user = _get_user(db, user_id)
    if user.status == UserStatus.SUSPENDED:
        raise ServiceException(status_code=409, title="Conflict", detail="La cuenta ya está suspendida.")
    if user.status == UserStatus.PENDING_DELETION and user.deletion_requested_by_admin_id is not None:
        raise ServiceException(
            status_code=409, title="Conflict", detail="La cuenta ya se está eliminando a pedido del titular."
        )

    summary = closure_summary(user)
    _ensure_not_blocked(
        summary,
        "El usuario tiene una reserva en curso. Vas a poder suspenderlo cuando termine.",
    )

    _close_down(db, user)

    user.status = UserStatus.SUSPENDED
    user.suspended_at = _now()
    user.suspended_by_admin_id = admin_id
    user.suspension_reason = reason
    # A suspension replaces a deletion the user had asked for: if they still want it,
    # they ask support, and an admin schedules it.
    user.deletion_requested_at = None
    user.deletion_scheduled_at = None
    db.add(user)
    db.commit()
    db.refresh(user)

    send_account_suspended_email(user.email)
    logger.info(f"[ACCOUNT] Cuenta suspendida: user_id={user.id} admin_id={admin_id}")
    return user


def reactivate(db: Session, user_id: UUID, admin_id: UUID | None) -> models.User:
    user = _get_user(db, user_id)
    if user.status != UserStatus.SUSPENDED:
        raise ServiceException(status_code=409, title="Conflict", detail="Solo se puede reactivar una cuenta suspendida.")

    parking_client.restore_owner_spots(user.id)

    user.status = UserStatus.ACTIVE
    user.suspended_at = None
    user.suspended_by_admin_id = None
    user.suspension_reason = None
    db.add(user)
    db.commit()
    db.refresh(user)

    send_account_reactivated_email(user.email)
    logger.info(f"[ACCOUNT] Cuenta reactivada: user_id={user.id} admin_id={admin_id}")
    return user


def admin_request_deletion(db: Session, user_id: UUID, admin_id: UUID | None, reason: str) -> models.User:
    """An admin deletes the account because its holder asked for it outside the app (by
    email, a letter...) -- e.g. a suspended user, who can't log in. Same effects as the
    user doing it, but with no grace period, it can't be cancelled by logging in, and who
    did it and why is kept."""
    user = _get_user(db, user_id)
    if user.status == UserStatus.PENDING_DELETION and user.deletion_requested_by_admin_id is not None:
        raise ServiceException(status_code=409, title="Conflict", detail="La cuenta ya se está eliminando.")

    summary = closure_summary(user)
    _ensure_not_blocked(
        summary,
        "El usuario tiene una reserva en curso. Vas a poder eliminar la cuenta cuando termine.",
    )

    _close_down(db, user)

    now = _now()
    user.status = UserStatus.PENDING_DELETION
    user.deletion_requested_at = now
    user.deletion_scheduled_at = now
    user.deletion_requested_by_admin_id = admin_id
    user.deletion_reason = reason
    db.add(user)
    db.commit()
    db.refresh(user)

    send_account_deletion_scheduled_email(user.email, format_date(now), can_cancel=False)
    logger.info(f"[ACCOUNT] Eliminación pedida por admin: user_id={user.id} admin_id={admin_id}")

    finalize_deletion(db, user)
    db.refresh(user)
    return user


# -------------------------
# Final wipe (background job)
# -------------------------


def finalize_deletion(db: Session, user: models.User) -> bool:
    """Wipes the personal data of an account whose deletion is due. Returns False (and
    leaves it pending, to try again on the next run) while ParkLink still owes the owner
    money -- paying them needs their payout details."""
    if user.status != UserStatus.PENDING_DELETION or user.deletion_scheduled_at is None:
        return False
    if _as_utc(user.deletion_scheduled_at) > _now():
        return False

    spot_ids = parking_client.list_owner_spot_ids(user.id)
    summary = booking_client.get_account_closure_summary(user.id, spot_ids)
    if int(summary.get("pending_payout_count", 0)) > 0:
        logger.info(f"[ACCOUNT] Eliminación de user_id={user.id} en espera: tiene pagos pendientes")
        return False

    # The account can't do anything new since it started closing, but these are cheap and
    # idempotent -- re-run them in case something slipped in (or failed) meanwhile.
    booking_client.cancel_account_bookings(user.id, spot_ids)
    parking_client.archive_owner_spots(user.id)
    booking_client.anonymize_account_bookings(user.id)
    notifications_client.delete_device_tokens(user.id)
    delete_avatar_file(user.avatar_url)

    # Last mail to the real address, before it's wiped.
    send_account_deleted_email(user.email)

    db.query(models.Vehicle).filter(models.Vehicle.user_id == user.id).delete(synchronize_session=False)
    db.query(models.VerificationToken).filter(models.VerificationToken.user_id == user.id).delete(
        synchronize_session=False
    )
    targets = [value for value in (user.email, user.phone, user.pending_email, user.pending_phone) if value]
    if targets:
        db.query(models.RegistrationVerification).filter(
            models.RegistrationVerification.target.in_(targets)
        ).delete(synchronize_session=False)
    db.query(models.RefreshToken).filter(models.RefreshToken.user_id == user.id).delete(synchronize_session=False)

    user.first_name, user.last_name = DELETED_NAME
    user.email = f"eliminado-{user.id.hex}@{DELETED_EMAIL_DOMAIN}"
    user.phone = None
    user.pending_email = None
    user.pending_phone = None
    user.dni = None
    user.birth_date = None
    user.avatar_url = None
    user.password_hash = security.hash_password(secrets.token_urlsafe(32))
    user.cbu = None
    user.payout_titular = None
    user.cuil = None
    user.payout_info_updated_at = None
    user.email_verified = False
    user.phone_verified = False
    user.status = UserStatus.DELETED
    user.deleted_at = _now()
    db.add(user)
    db.commit()

    logger.info(f"[ACCOUNT] Cuenta eliminada (datos anonimizados): user_id={user.id}")
    return True


def finalize_due_deletions(db: Session) -> int:
    """Run by the background job in main.py. One failing account (a service down, say)
    doesn't stop the rest; it's simply retried on the next run."""
    due = (
        db.query(models.User)
        .filter(models.User.status == UserStatus.PENDING_DELETION, models.User.deletion_scheduled_at <= _now())
        .all()
    )
    deleted = 0
    for user in due:
        try:
            if finalize_deletion(db, user):
                deleted += 1
        except Exception as exc:  # noqa: BLE001 - keep going with the other accounts
            db.rollback()
            logger.error(f"[ACCOUNT] Falló la eliminación de user_id={user.id}: {exc}")
    return deleted
