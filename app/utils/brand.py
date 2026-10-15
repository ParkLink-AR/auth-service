"""ParkLink official brand tokens (colors, logo), shared by emails and web pages.

Source of truth: anteproyecto_Parklink/tex/anexo_colorimetria.tex (paleta oficial)
and landing-webpage/styles.css (derived UI tones). Do not use colors outside
this palette in transactional emails or auth-service HTML pages.
"""

NAVY = "#042347"
NAVY_DARK = "#021528"
TEAL = "#168B8D"
TEAL_SOFT = "#1AADAF"
WHITE = "#FFFFFF"
GRAY_BG = "#F7F8FA"
GRAY_MID = "#E2E8F0"
TEXT = "#1E2D3D"
TEXT_MUTED = "#64778A"
BORDER = "#DDE3EC"

# Also mirrored locally at app/static/logo-letras.png (served via
# app.mount("/static", ...) in main.py) for use once auth-service itself has
# a stable public URL. Emails and the browser-facing pages linked from them
# need a logo URL that resolves from any inbox/network today, so they point
# at the landing page instead, which is already public on GitHub Pages.
# This is the wordmark-only variant (~5.3:1 aspect ratio), not the square icon. It lives
# under assets/logos/ on the landing page -- if the landing page moves it again, emails show
# a broken image, so update this along with it.
LOGO_URL = "https://www.parklink.com.ar/assets/logos/logo-letras.png"
