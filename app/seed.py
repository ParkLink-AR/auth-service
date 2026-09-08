"""Cuentas de prueba fijas, garantizadas en cada arranque (idempotente).

Ambas quedan con email y teléfono verificados y status ACTIVE, así que se
puede hacer login directo sin pasar por el wizard de registro.

    a@test.com / 11223344Aa
    b@test.com / 11223344Aa

Nunca se llama en producción (ENVIRONMENT=production) -- ver main.py.
"""

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User, UserStatus
from app.security import hash_password

TEST_PASSWORD = "11223344Aa"

_TEST_USERS = [
    {
        "email": "a@test.com",
        "first_name": "Test",
        "last_name": "A",
        "phone": "+541100000001",
        "dni": "40000001",
    },
    {
        "email": "b@test.com",
        "first_name": "Test",
        "last_name": "B",
        "phone": "+541100000002",
        "dni": "40000002",
    },
]


def seed_test_users(db: Session) -> None:
    """Crea a@test.com y b@test.com si no existen. Seguro de llamar en cada
    startup: chequea por email antes de insertar y tolera colisiones de
    phone/dni (por si alguien registró esos valores a mano)."""
    if settings.ENVIRONMENT.lower() == "production":
        logger.error("[SEED] bloqueado: no se siembran cuentas de prueba en producción")
        return

    password_hash = hash_password(TEST_PASSWORD)

    for spec in _TEST_USERS:
        exists = db.query(User).filter(User.email == spec["email"]).first()
        if exists is not None:
            continue

        db.add(
            User(
                email=spec["email"],
                first_name=spec["first_name"],
                last_name=spec["last_name"],
                phone=spec["phone"],
                dni=spec["dni"],
                password_hash=password_hash,
                email_verified=True,
                phone_verified=True,
                status=UserStatus.ACTIVE,
            )
        )
        try:
            db.commit()
            logger.info(f"[SEED] cuenta de prueba creada: {spec['email']}")
        except IntegrityError:
            db.rollback()
            logger.warning(
                f"[SEED] {spec['email']} no se pudo crear (phone/dni ya en uso), se omite"
            )
