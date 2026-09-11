from __future__ import annotations

import httpx
from loguru import logger

from app.config import settings
from app.exceptions.handler import ServiceException

WHATSAPP_API_URL = "https://graph.facebook.com/{version}/{phone_number_id}/messages"


def send_registration_whatsapp(to_phone: str, code: str) -> None:
    """Sends the 6-digit signup verification code via WhatsApp (Meta Cloud
    API, AUTHENTICATION template -- the app owns the code lifecycle itself,
    same as the email flow). Requires the template to already be approved
    in Meta Business Manager under WHATSAPP_TEMPLATE_NAME/WHATSAPP_TEMPLATE_LANG."""

    if not settings.WHATSAPP_ACCESS_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
        logger.info(f"[WHATSAPP][DEV] Código de verificación para {to_phone}: {code}")
        return

    url = WHATSAPP_API_URL.format(
        version=settings.WHATSAPP_API_VERSION,
        phone_number_id=settings.WHATSAPP_PHONE_NUMBER_ID,
    )
    body = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        # Graph API wants digits only (country code + number), no leading "+".
        "to": to_phone.lstrip("+"),
        "type": "template",
        "template": {
            "name": settings.WHATSAPP_TEMPLATE_NAME,
            "language": {"code": settings.WHATSAPP_TEMPLATE_LANG},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": code}],
                }
            ],
        },
    }

    try:
        response = httpx.post(
            url,
            json=body,
            headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
            timeout=10.0,
        )
    except httpx.HTTPError as e:
        logger.error(f"[WHATSAPP] Error de red enviando mensaje a {to_phone}: {e}")
        raise ServiceException(
            status_code=502, title="Bad Gateway", detail="Error sending WhatsApp message."
        )

    if response.status_code >= 400:
        logger.error(f"[WHATSAPP] Graph API devolvió status={response.status_code} body={response.text}")
        raise ServiceException(
            status_code=502, title="Bad Gateway", detail="Error sending WhatsApp message."
        )

    logger.debug(f"[WHATSAPP] Mensaje enviado a {to_phone}: {response.json().get('messages')}")
