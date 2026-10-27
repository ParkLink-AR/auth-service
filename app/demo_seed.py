"""Usuarios de ejemplo para la demo: los dueños de las cocheras demo y los conductores que
figuran en sus reseñas. Existen para que la app muestre nombres reales ("Publicada por Marcelo
Giménez", "Reseña de Camila Torres") y no ids sueltos.

Son cuentas de verdad en la base pero nadie puede entrar con ellas: la contraseña es un hash de un
valor aleatorio que no se guarda en ningún lado. Los ids son fijos y los comparten parking-service
(dueños, ver src/demo/demo-content.ts) y booking-service (conductores, ver
internal/domain/constants/demo.go), que no consultan a este servicio para armarlos.

Solo se cargan con SEED_DEMO_DATA=true y es idempotente: lo que ya existe no se toca.
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.models import AccountType, User, UserStatus
from app.security import hash_password

DEMO_EMAIL_DOMAIN = "demo.parklink.com.ar"

# (nombre, apellido)
OWNERS = [
    ("Marcelo", "Giménez"), ("Patricia", "Alonso"), ("Roberto", "Sánchez"), ("Liliana", "Cabrera"),
    ("Héctor", "Medina"), ("Silvia", "Ortega"), ("Gustavo", "Peralta"), ("Mónica", "Vidal"),
    ("Raúl", "Domínguez"), ("Beatriz", "Funes"),
]

_FIRST_NAMES = [
    "Camila", "Lucas", "Valentina", "Mateo", "Julieta", "Nicolás", "Martina", "Tomás", "Agustina", "Bruno",
    "Sofía", "Joaquín", "Lucía", "Federico", "Florencia", "Matías", "Carolina", "Diego", "Paula", "Sebastián",
]
_LAST_NAMES = [
    "Torres", "Fernández", "Acosta", "Sosa", "Romero", "Benítez", "Ríos", "Aguirre", "Molina", "Castro",
    "Domínguez", "Herrera", "Ruiz", "Díaz", "Gómez", "Álvarez", "Silva", "Rojas", "Núñez", "Ibáñez",
]
DRIVER_COUNT = 60


def _drivers() -> list[tuple[str, str]]:
    # 20 nombres x 20 apellidos, recorridos de a saltos para que no se repitan en 60 conductores.
    return [(_FIRST_NAMES[n % 20], _LAST_NAMES[(n * 7 + n // 20) % 20]) for n in range(DRIVER_COUNT)]


def owner_id(index: int) -> uuid.UUID:
    return uuid.UUID(f"0e000000-0000-4000-8000-{index:012d}")


def driver_id(index: int) -> uuid.UUID:
    return uuid.UUID(f"de000000-0000-4000-8000-{index:012d}")


def _slug(text: str) -> str:
    table = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")
    return text.translate(table).lower().replace(" ", "")


def _email(first: str, last: str, index: int) -> str:
    # El número evita choques si dos personas comparten nombre y apellido.
    return f"{_slug(first)}.{_slug(last)}.{index}@{DEMO_EMAIL_DOMAIN}"


def seed_demo_users(db: Session) -> int:
    """Crea los usuarios de ejemplo que falten. Devuelve cuántos creó."""
    people = [
        (owner_id(i + 1), first, last, AccountType.OWNER) for i, (first, last) in enumerate(OWNERS)
    ] + [
        (driver_id(i + 1), first, last, AccountType.DRIVER) for i, (first, last) in enumerate(_drivers())
    ]
    existing = {row[0] for row in db.query(User.id).filter(User.id.in_([p[0] for p in people])).all()}

    # Un solo hash para todos: es un valor aleatorio que se descarta, nadie puede iniciar sesión.
    unusable_hash = hash_password(secrets.token_urlsafe(48))
    now = datetime.now(timezone.utc)
    created = 0
    for position, (user_id, first, last, account_type) in enumerate(people):
        if user_id in existing:
            continue
        db.add(
            User(
                id=user_id,
                email=_email(first, last, position + 1),
                first_name=first,
                last_name=last,
                account_type=account_type,
                status=UserStatus.ACTIVE,
                password_hash=unusable_hash,
                email_verified=True,
                phone_verified=True,
                created_at=now - timedelta(days=30 + (position * 5) % 240),
            )
        )
        created += 1
    if created:
        db.commit()
        logger.info(f"[DEMO] {created} usuarios de ejemplo creados")
    return created
