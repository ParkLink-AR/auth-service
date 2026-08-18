# config.py
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    DATABASE_URL: str

    # JWT
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Brevo (transactional email)
    BREVO_API_KEY: str = ""
    EMAIL_FROM: str = "no-reply@mail.parklink.com.ar"
    EMAIL_FROM_NAME: str = "ParkLink Argentina"

    # Twilio (SMS) -- plain SMS send, not Twilio Verify: we own the code
    # lifecycle ourselves, same as the email flow.
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

    # Skips email verification requirement at login (useful for local dev/tests)
    SKIP_EMAIL_VERIFICATION: bool = False

    # Email/SMS verification are 6-digit codes the user types in the app, not
    # a clicked link -- keep their lifetime short.
    EMAIL_VERIFICATION_CODE_EXPIRE_MINUTES: int = 15
    PHONE_VERIFICATION_CODE_EXPIRE_MINUTES: int = 15
    # Once a signup code is confirmed, how long the "verified" state stays
    # valid to finish the rest of the wizard (the other channel + personal
    # data step) before having to re-verify.
    REGISTRATION_VERIFICATION_GRACE_MINUTES: int = 30
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30

    model_config = ConfigDict(
        extra="ignore", env_file=".env", env_file_encoding="utf-8"
    )


settings = Settings()
