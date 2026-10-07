from __future__ import annotations

import httpx
from loguru import logger

from app.config import settings
from app.exceptions.handler import ServiceException
from .email_templates import (
    get_account_deleted_email_html,
    get_account_deletion_cancelled_email_html,
    get_account_deletion_scheduled_email_html,
    get_account_reactivated_email_html,
    get_account_suspended_email_html,
    get_email_change_email_html,
    get_reset_password_email_html,
    get_verification_email_html,
)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def send_email_html(to_email: str, subject: str, html_body: str) -> None:
    """Send a transactional email through the Brevo (Sendinblue) REST API."""

    if not settings.BREVO_API_KEY:
        logger.warning(
            f"[MAIL] BREVO_API_KEY no configurada, se omite el envío a {to_email}"
        )
        return

    payload = {
        "sender": {"name": settings.EMAIL_FROM_NAME, "email": settings.EMAIL_FROM},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_body,
    }
    headers = {
        "api-key": settings.BREVO_API_KEY,
        "accept": "application/json",
        "content-type": "application/json",
    }

    try:
        response = httpx.post(BREVO_API_URL, json=payload, headers=headers, timeout=10.0)
    except httpx.HTTPError as e:
        logger.error(f"[MAIL] Error de red enviando email a {to_email}: {e}")
        raise ServiceException(
            status_code=502,
            title="Bad Gateway",
            detail="Error sending email.",
        )

    if response.status_code >= 400:
        logger.error(
            f"[MAIL] Brevo devolvió status={response.status_code} body={response.text}"
        )
        raise ServiceException(
            status_code=502,
            title="Bad Gateway",
            detail="Error sending email.",
        )

    logger.debug(f"[MAIL] Email enviado a {to_email}: {response.json().get('messageId')}")


def send_verification_email(to_email: str, code: str) -> None:
    if not settings.BREVO_API_KEY:
        logger.info(f"[MAIL][DEV] Código de verificación para {to_email}: {code}")

    html_content = get_verification_email_html(code)
    send_email_html(
        to_email=to_email,
        subject="Verificá tu cuenta - ParkLink",
        html_body=html_content,
    )


def send_email_change_email(to_email: str, code: str) -> None:
    if not settings.BREVO_API_KEY:
        logger.info(f"[MAIL][DEV] Código de cambio de email para {to_email}: {code}")

    html_content = get_email_change_email_html(code)
    send_email_html(
        to_email=to_email,
        subject="Confirmá tu nuevo email - ParkLink",
        html_body=html_content,
    )


def send_reset_password_email(to_email: str, code: str) -> None:
    if not settings.BREVO_API_KEY:
        logger.info(f"[MAIL][DEV] Código de restablecimiento para {to_email}: {code}")

    html_content = get_reset_password_email_html(code)
    send_email_html(
        to_email=to_email,
        subject="Restablecer tu contraseña - ParkLink",
        html_body=html_content,
    )


# -------------------------
# Account lifecycle notices -- best effort: a mail failure is logged, never raised, so it
# can't undo an account change that already happened.
# -------------------------


def _send_notice(to_email: str, subject: str, html_body: str) -> None:
    try:
        send_email_html(to_email=to_email, subject=subject, html_body=html_body)
    except ServiceException:
        logger.warning(f"[MAIL] No se pudo enviar '{subject}' a {to_email}")


def send_account_deletion_scheduled_email(to_email: str, deletion_date: str, can_cancel: bool) -> None:
    _send_notice(
        to_email,
        "Tu cuenta de ParkLink se va a eliminar",
        get_account_deletion_scheduled_email_html(deletion_date, can_cancel, settings.SUPPORT_EMAIL),
    )


def send_account_deletion_cancelled_email(to_email: str) -> None:
    _send_notice(
        to_email,
        "Cancelaste la eliminación de tu cuenta de ParkLink",
        get_account_deletion_cancelled_email_html(settings.SUPPORT_EMAIL),
    )


def send_account_deleted_email(to_email: str) -> None:
    _send_notice(to_email, "Eliminamos tu cuenta de ParkLink", get_account_deleted_email_html(settings.SUPPORT_EMAIL))


def send_account_suspended_email(to_email: str) -> None:
    _send_notice(to_email, "Tu cuenta de ParkLink fue suspendida", get_account_suspended_email_html(settings.SUPPORT_EMAIL))


def send_account_reactivated_email(to_email: str) -> None:
    _send_notice(
        to_email, "Tu cuenta de ParkLink está activa otra vez", get_account_reactivated_email_html(settings.SUPPORT_EMAIL)
    )
