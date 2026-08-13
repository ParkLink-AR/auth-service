# config.py
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    DATABASE_URL: str

    # Public URL this service is reachable at, used to build absolute links
    # (logo, verify-email/reset-password pages) inside transactional emails.
    PUBLIC_BASE_URL: str = "http://localhost:8000"

    # JWT
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Brevo (transactional email)
    BREVO_API_KEY: str = ""
    EMAIL_FROM: str = "no-reply@mail.parklink.com.ar"
    EMAIL_FROM_NAME: str = "ParkLink Argentina"

    # Skips email verification requirement at login (useful for local dev/tests)
    SKIP_EMAIL_VERIFICATION: bool = False

    EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS: int = 24
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30

    model_config = ConfigDict(
        extra="ignore", env_file=".env", env_file_encoding="utf-8"
    )


settings = Settings()
