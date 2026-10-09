from __future__ import annotations

import time

import httpx
from loguru import logger

from app.config import settings
from app.exceptions.handler import ServiceException

TWILIO_API_URL = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

# How long to wait before the one retry of a send that couldn't even connect to Twilio.
_CONNECT_RETRY_DELAY_SECONDS = 1.0


def send_registration_sms(to_phone: str, code: str) -> None:
    """Sends the 6-digit signup verification code via Twilio (plain SMS, not
    Twilio Verify -- the app owns the code lifecycle itself, same as email)."""

    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.info(f"[SMS][DEV] Código de verificación para {to_phone}: {code}")
        return

    url = TWILIO_API_URL.format(account_sid=settings.TWILIO_ACCOUNT_SID)
    body = {
        "To": to_phone,
        "From": settings.TWILIO_FROM_NUMBER,
        "Body": f"Tu código de verificación de ParkLink es {code}. Vence en 15 minutos.",
    }

    def post() -> httpx.Response:
        return httpx.post(
            url,
            data=body,
            auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            timeout=10.0,
        )

    try:
        try:
            response = post()
        except httpx.ConnectError as e:
            # Couldn't even reach Twilio (e.g. a momentary DNS failure: "Temporary failure
            # in name resolution") -- nothing was sent, so one retry can't double-send it.
            # Any other failure (a timeout mid-request) might already have sent it: no retry.
            logger.warning(f"[SMS] No se pudo conectar con Twilio para {to_phone}, reintentando: {e}")
            time.sleep(_CONNECT_RETRY_DELAY_SECONDS)
            response = post()
    except httpx.HTTPError as e:
        logger.error(f"[SMS] Error de red enviando SMS a {to_phone}: {e}")
        raise ServiceException(status_code=502, title="Bad Gateway", detail="Error sending SMS.")

    if response.status_code >= 400:
        logger.error(f"[SMS] Twilio devolvió status={response.status_code} body={response.text}")
        raise ServiceException(status_code=502, title="Bad Gateway", detail="Error sending SMS.")

    logger.debug(f"[SMS] SMS enviado a {to_phone}: {response.json().get('sid')}")
