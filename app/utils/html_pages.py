"""Standalone HTML pages served by auth-service for the links mailed to users
(email verification result, password reset form), styled to match landing-webpage.
"""

import json

from app.utils.brand import (
    BORDER,
    GRAY_BG,
    LOGO_URL,
    NAVY,
    NAVY_DARK,
    TEAL,
    TEAL_SOFT,
    TEXT,
    TEXT_MUTED,
    WHITE,
)


def _shell(title: str, body_html: str, extra_script: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} · ParkLink</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {{
    --navy: {NAVY}; --navy-dark: {NAVY_DARK}; --teal: {TEAL}; --teal-soft: {TEAL_SOFT};
    --white: {WHITE}; --gray-bg: {GRAY_BG}; --text: {TEXT}; --text-muted: {TEXT_MUTED}; --border: {BORDER};
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
    background: var(--gray-bg); font-family: 'Inter', sans-serif; color: var(--text); padding: 24px;
  }}
  .card {{
    width: 100%; max-width: 420px; background: var(--white); border: 1px solid var(--border);
    border-radius: 16px; padding: 40px 32px; text-align: center;
    box-shadow: 0 2px 20px rgba(4,35,71,0.08);
  }}
  .logo {{ height: 34px; margin-bottom: 26px; }}
  h1 {{ font-family: 'Space Grotesk', sans-serif; font-size: 1.3rem; color: var(--navy); margin: 0 0 10px; }}
  p {{ font-size: 0.9rem; color: var(--text-muted); line-height: 1.65; margin: 0 0 22px; }}
  .icon {{
    width: 56px; height: 56px; border-radius: 50%; display: flex; align-items: center;
    justify-content: center; margin: 0 auto 18px;
  }}
  .icon.ok {{ background: rgba(22,139,141,0.1); color: var(--teal); }}
  .icon.err {{ background: rgba(198,40,40,0.08); color: #C62828; }}
  .btn {{
    display: inline-flex; align-items: center; justify-content: center; width: 100%;
    background: var(--teal); color: white; border: none; padding: 13px 20px;
    border-radius: 8px; font-size: 0.9rem; font-weight: 600; text-decoration: none;
    cursor: pointer; transition: background 0.18s; font-family: 'Inter', sans-serif;
  }}
  .btn:hover {{ background: var(--teal-soft); }}
  .btn:disabled {{ opacity: 0.6; cursor: default; }}
  input {{
    width: 100%; padding: 12px 14px; border: 1.5px solid var(--border); border-radius: 8px;
    font-size: 0.9rem; margin-bottom: 12px; font-family: 'Inter', sans-serif; color: var(--text);
  }}
  input:focus {{ outline: none; border-color: var(--teal); }}
  form {{ text-align: left; }}
  .msg {{ font-size: 0.82rem; margin: 0 0 14px; display: none; }}
  .msg.show {{ display: block; }}
  .msg.err {{ color: #C62828; }}
  .msg.ok {{ color: var(--teal); }}
  .foot {{ margin-top: 24px; font-size: 0.72rem; color: var(--text-muted); margin-bottom: 0; }}
</style>
</head>
<body>
  <div class="card">
    <img src="{LOGO_URL}" alt="ParkLink" class="logo">
    {body_html}
  </div>
  {extra_script}
</body>
</html>"""


_CHECK_ICON = '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>'
_CROSS_ICON = '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 6L6 18M6 6l12 12"/></svg>'


def get_email_verified_page() -> str:
    body = f"""
    <div class="icon ok">{_CHECK_ICON}</div>
    <h1>¡Cuenta activada!</h1>
    <p style="margin-bottom:0;">Tu email fue verificado correctamente. Ya podés volver a la app de ParkLink e iniciar sesión.</p>
    """
    return _shell("Cuenta activada", body)


def get_invalid_link_page(message: str) -> str:
    body = f"""
    <div class="icon err">{_CROSS_ICON}</div>
    <h1>El link no es válido</h1>
    <p style="margin-bottom:0;">{message}</p>
    """
    return _shell("Link inválido", body)


def get_reset_password_form_page(token: str) -> str:
    body = """
    <h1>Restablecé tu contraseña</h1>
    <p>Elegí una nueva contraseña para tu cuenta de ParkLink.</p>
    <form id="reset-form">
      <input type="password" id="password" placeholder="Nueva contraseña" required minlength="8">
      <input type="password" id="password2" placeholder="Repetí la contraseña" required minlength="8">
      <p class="msg err" id="error-msg"></p>
      <p class="msg ok" id="success-msg"></p>
      <button type="submit" class="btn" id="submit-btn">Restablecer contraseña</button>
    </form>
    <p class="foot">Debe tener al menos 8 caracteres, una mayúscula, una minúscula y un número.</p>
    """
    script = f"""
  <script>
    const form = document.getElementById('reset-form');
    const errorMsg = document.getElementById('error-msg');
    const successMsg = document.getElementById('success-msg');
    const submitBtn = document.getElementById('submit-btn');
    const token = {json.dumps(token)};

    form.addEventListener('submit', async (e) => {{
      e.preventDefault();
      errorMsg.classList.remove('show');
      successMsg.classList.remove('show');

      const password = document.getElementById('password').value;
      const password2 = document.getElementById('password2').value;

      if (password !== password2) {{
        errorMsg.textContent = 'Las contraseñas no coinciden.';
        errorMsg.classList.add('show');
        return;
      }}

      submitBtn.disabled = true;
      submitBtn.textContent = 'Restableciendo...';

      try {{
        const res = await fetch('/auth/password-reset/confirm', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ token: token, new_password: password }})
        }});
        const data = await res.json();

        if (!res.ok) {{
          errorMsg.textContent = data.detail || 'No se pudo restablecer la contraseña.';
          errorMsg.classList.add('show');
          submitBtn.disabled = false;
          submitBtn.textContent = 'Restablecer contraseña';
          return;
        }}

        successMsg.textContent = 'Contraseña actualizada. Ya podés iniciar sesión en la app.';
        successMsg.classList.add('show');
        form.querySelectorAll('input, button').forEach(el => el.disabled = true);
      }} catch (err) {{
        errorMsg.textContent = 'Error de conexión. Intentá de nuevo.';
        errorMsg.classList.add('show');
        submitBtn.disabled = false;
        submitBtn.textContent = 'Restablecer contraseña';
      }}
    }});
  </script>
    """
    return _shell("Restablecer contraseña", body, extra_script=script)
