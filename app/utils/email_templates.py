"""Email templates for ParkLink (sent via Brevo), styled to match landing-webpage."""

from typing import Optional

from app.utils.brand import (
    BORDER,
    GRAY_BG,
    LOGO_URL,
    NAVY,
    NAVY_DARK,
    TEAL,
    TEAL_SOFT,
    TEXT_MUTED,
    WHITE,
)

FONT_STACK = "'Segoe UI', Roboto, Helvetica, Arial, sans-serif"


def _button(label: str, url: str) -> str:
    return f"""
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center" style="margin: 26px auto;">
      <tr>
        <td align="center" bgcolor="{TEAL}" style="border-radius: 8px;">
          <a href="{url}" target="_blank"
             style="display: inline-block; padding: 14px 34px; font-family: {FONT_STACK}; font-size: 15px; font-weight: 700; color: {WHITE}; text-decoration: none; border-radius: 8px;">
            {label}
          </a>
        </td>
      </tr>
    </table>
    """


def _fallback_link(url: str) -> str:
    return f"""
    <p style="font-size: 12.5px; color: {TEXT_MUTED}; line-height: 1.6; margin: 0 0 6px;">
      ¿El botón no funciona? Copiá y pegá este link en tu navegador:
    </p>
    <p style="margin: 0 0 22px; word-break: break-all;">
      <a href="{url}" target="_blank" style="color: {TEAL}; font-size: 12.5px; text-decoration: underline;">{url}</a>
    </p>
    """


def _base_template(
    preheader: str,
    greeting: str,
    message_html: str,
    expiration_text: str,
    button_label: Optional[str] = None,
    button_url: Optional[str] = None,
) -> str:
    action_block = (
        f"{_button(button_label, button_url)}{_fallback_link(button_url)}"
        if button_url
        else ""
    )
    return f"""
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="light">
  <title>ParkLink</title>
</head>
<body style="margin: 0; padding: 0; background-color: {GRAY_BG}; font-family: {FONT_STACK};">
  <span style="display: none; visibility: hidden; opacity: 0; overflow: hidden; height: 0; width: 0;">{preheader}</span>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color: {GRAY_BG}; padding: 40px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width: 520px; background-color: {WHITE}; border-radius: 14px; overflow: hidden; border: 1px solid {BORDER};">
          <tr>
            <td align="center" style="padding: 34px 24px 18px; border-bottom: 1px solid {BORDER};">
              <img src="{LOGO_URL}" alt="ParkLink" width="170" style="display: block; width: 170px; height: auto;">
            </td>
          </tr>
          <tr>
            <td style="padding: 34px 36px 6px; text-align: center;">
              <p style="margin: 0 0 14px; font-family: {FONT_STACK}; font-size: 20px; font-weight: 700; color: {NAVY};">{greeting}</p>
              <div style="font-size: 14.5px; color: {TEXT_MUTED}; line-height: 1.7;">{message_html}</div>
            </td>
          </tr>
          <tr>
            <td style="padding: 4px 36px 8px; text-align: center;">
              {action_block}
              <p style="font-size: 12.5px; color: #9A6B00; background-color: #FFF6E0; border: 1px solid #F5E2AD; border-radius: 6px; padding: 10px 14px; margin: 0;">
                {expiration_text}
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding: 20px 36px 32px; text-align: center;">
              <p style="font-size: 12.5px; color: {TEXT_MUTED}; background-color: {GRAY_BG}; padding: 12px 14px; border-radius: 6px; margin: 0;">
                Si no fuiste vos quien solicitó esto, podés ignorar este correo con tranquilidad.
              </p>
            </td>
          </tr>
          <tr>
            <td align="center" style="background-color: {NAVY_DARK}; padding: 20px 24px;">
              <p style="margin: 0; font-family: {FONT_STACK}; font-size: 12px; font-weight: 700; letter-spacing: 0.02em;">
                <span style="color: rgba(255,255,255,0.55);">Park</span><span style="color: {TEAL_SOFT};">Link</span>
              </p>
              <p style="margin: 6px 0 0; font-size: 11px; color: rgba(255,255,255,0.35);">
                &copy; 2026 ParkLink &middot; Estacionar en la ciudad, sin el caos.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def get_verification_email_html(code: str) -> str:
    code_block = f"""
    <div style="font-family: {FONT_STACK}; font-size: 34px; font-weight: 700; letter-spacing: 10px;
                color: {NAVY}; background-color: {GRAY_BG}; border: 1px solid {BORDER};
                border-radius: 10px; padding: 16px 10px; margin: 18px 0; text-align: center;">
      {code}
    </div>
    """
    return _base_template(
        preheader="Tu código para activar tu cuenta de ParkLink.",
        greeting="¡Bienvenido a ParkLink!",
        message_html=(
            "<p style='margin:0;'>Ingresá este código en la app para activar tu cuenta y "
            f"empezar a reservar y publicar cocheras en tu ciudad:</p>{code_block}"
        ),
        expiration_text="Este código vence en 15 minutos.",
    )


def get_email_change_email_html(code: str) -> str:
    code_block = f"""
    <div style="font-family: {FONT_STACK}; font-size: 34px; font-weight: 700; letter-spacing: 10px;
                color: {NAVY}; background-color: {GRAY_BG}; border: 1px solid {BORDER};
                border-radius: 10px; padding: 16px 10px; margin: 18px 0; text-align: center;">
      {code}
    </div>
    """
    return _base_template(
        preheader="Tu código para confirmar tu nuevo email de ParkLink.",
        greeting="Confirmá tu nuevo email",
        message_html=(
            "<p style='margin:0;'>Recibimos una solicitud para cambiar el email de tu cuenta a "
            f"esta dirección. Ingresá este código en la app para confirmarlo:</p>{code_block}"
        ),
        expiration_text="Este código vence en 15 minutos.",
    )


def get_reset_password_email_html(code: str) -> str:
    code_block = f"""
    <div style="font-family: {FONT_STACK}; font-size: 34px; font-weight: 700; letter-spacing: 10px;
                color: {NAVY}; background-color: {GRAY_BG}; border: 1px solid {BORDER};
                border-radius: 10px; padding: 16px 10px; margin: 18px 0; text-align: center;">
      {code}
    </div>
    """
    return _base_template(
        preheader="Tu código para restablecer tu contraseña de ParkLink.",
        greeting="Restablecé tu contraseña",
        message_html=(
            "<p style='margin:0;'>Recibimos una solicitud para restablecer tu contraseña. "
            f"Ingresá este código en la app para elegir una nueva:</p>{code_block}"
        ),
        expiration_text="Este código vence en 30 minutos.",
    )
