# auth-service

Microservicio de autenticación de **ParkLink**: registro, login, tokens (access + refresh),
sesiones multi-dispositivo, verificación de email y reseteo de contraseña.

Construido con **FastAPI**, **PostgreSQL** (SQLAlchemy + Alembic) y **JWT**. Los emails
transaccionales se envían con **Brevo**.

## Qué implementa

### Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/auth/register` | Registra un usuario nuevo (email + password, teléfono opcional). Envía email de verificación. |
| POST | `/auth/login` | Autentica con email o teléfono + password. Devuelve `access_token` + `refresh_token`. |
| POST | `/auth/refresh` | Rota el refresh token: invalida el usado y devuelve un par nuevo. |
| POST | `/auth/logout` | Invalida el refresh token de la sesión actual (un solo dispositivo). |
| GET | `/auth/sessions` | Lista las sesiones/dispositivos activos del usuario autenticado. |
| DELETE | `/auth/sessions/{session_id}` | Revoca una sesión puntual (ej: "cerrar sesión" en otro dispositivo). |
| POST | `/auth/email-verification/request` | Reenvía el código de verificación de email. |
| POST | `/auth/email-verification/confirm` | Confirma el email con el código recibido. |
| POST | `/auth/password-reset/request` | Solicita reseteo de contraseña (recibe el email, genera un token temporal). |
| POST | `/auth/password-reset/confirm` | Confirma el reseteo con el token recibido y la nueva contraseña. |
| GET | `/users/{id}` | Obtiene el perfil del usuario (sólo el propio usuario autenticado). |
| PUT | `/users/{id}` | Actualiza email y/o teléfono del propio usuario (dispara re-verificación si cambian). |
| DELETE | `/users/{id}` | Elimina (soft-delete) la cuenta propia. Requiere confirmar la contraseña actual. |
| GET | `/livez` / `/readyz` | Health checks (proceso vivo / conectividad a la DB). |

Todos los endpoints bajo `/users` y las rutas de sesiones requieren `Authorization: Bearer <access_token>`.

### Modelo de datos

```
users
├── id                  UUID (PK)
├── email               VARCHAR UNIQUE
├── phone               VARCHAR UNIQUE NULL
├── password_hash       TEXT
├── email_verified       BOOLEAN
├── phone_verified       BOOLEAN
├── status              ACTIVE / SUSPENDED / DELETED
├── created_at
├── updated_at
└── last_login_at

refresh_tokens
├── id                  UUID (PK)
├── user_id             FK -> users.id
├── token_hash          VARCHAR (sha256 del token; el token crudo nunca se persiste)
├── device_id
├── device_name
├── expires_at
├── revoked_at
├── created_at
├── last_used_at
└── ip_address

verification_tokens
├── id                  UUID (PK)
├── user_id             FK -> users.id
├── type                EMAIL / PHONE / PASSWORD_RESET
├── token_hash          VARCHAR (sha256 del token; el token crudo sólo va por email)
├── expires_at
├── used_at
└── created_at
```

`phone_verified` existe en el modelo pero **no hay flujo de verificación por SMS todavía**
(no se definió proveedor). Cuando se elija uno (Twilio, etc.) se agrega un endpoint análogo
a `email-verification`.

### Decisiones de diseño

- **JWT access token (corta duración, 15 min por defecto) + refresh token opaco (30 días)**:
  el refresh token es un valor random (`secrets.token_urlsafe`), no un JWT. Sólo se guarda su
  hash SHA-256 en `refresh_tokens`, para poder revocar sesiones sin que la base de datos sea
  en sí misma un secreto portador. Igual criterio para los `verification_tokens`.
- **Multi-sesión real**: cada login crea una fila en `refresh_tokens` con su `device_id` /
  `device_name` / `ip_address`. Un usuario puede tener N sesiones activas (una por dispositivo),
  listarlas (`GET /auth/sessions`) y revocarlas individualmente.
- **Rotación de refresh token**: cada `POST /auth/refresh` invalida el token usado y emite uno
  nuevo para el mismo dispositivo. Si un refresh token robado se reutiliza después de rotado,
  falla — señal de que ese token fue comprometido.
- **Verificación de email obligatoria para loguear** (configurable con `SKIP_EMAIL_VERIFICATION=true`
  para desarrollo/tests). Un usuario `SUSPENDED` no puede loguearse; uno `DELETED` da el mismo
  error genérico que credenciales inválidas (no revela que la cuenta existió).
- **Baja de cuenta = soft delete**: `DELETE /users/{id}` pide la contraseña actual, marca
  `status=DELETED`, anonimiza el email (así ese email vuelve a estar disponible para un
  registro nuevo), limpia el teléfono y revoca todas las sesiones activas. No se borra la fila.
- **Reset de contraseña revoca todas las sesiones** activas del usuario en todos los dispositivos.
- **`PUT /users/{id}` sólo actualiza `email`/`phone`**, porque es lo único que vive en la tabla
  `users` que diste. Ver más abajo la recomendación sobre un servicio de perfil aparte.
- **Sin roles/permisos todavía**: el esquema de `users` no tiene columna `role`, así que no se
  inventó una. El JWT sólo lleva el `user_id`. Si más adelante necesitás roles (ej. operador de
  un estacionamiento vs. conductor), es un cambio acotado: agregar la columna y usarla en el
  `sub`/claims del token.

### Seguridad

- Passwords con `pbkdf2_sha256` (vía `passlib`), nunca en texto plano.
- Refresh tokens y tokens de verificación/reset: sólo se persiste su hash SHA-256.
- Rate limiting básico (60s) para pedidos repetidos de verificación de email / reset de password.
- Respuestas genéricas en `password-reset/request` y `email-verification/request` (no revelan
  si el email existe en el sistema).
- El `task-definition.json` que estaba en el repo tenía una **API key real de Resend y
  credenciales de RDS del proyecto Bazaar anterior**, commiteadas en git. Se borró el archivo,
  pero si ese historial se comparte conviene rotar esa key (no es algo que se pueda hacer desde acá).

## ¿Otro microservicio para el perfil?

**Sí, tiene sentido separarlo.** El `auth-service` debería quedar enfocado únicamente en
identidad y credenciales (lo que ya tiene: email/teléfono, password, verificación, sesiones).
Todo lo que sea "perfil" — nombre, foto, vehículos del usuario, medios de pago guardados,
preferencias — encaja mejor en un `user-profile-service` (o directamente en el dominio que lo
consume, ej. `booking-service` si es específico de reservas) que:

- referencia al usuario por `user_id` (UUID) sin duplicar credenciales,
- puede evolucionar su esquema sin tocar el servicio de autenticación,
- no queda expuesto si alguna vez rotás JWT_SECRET o cambiás el flujo de login.

Es el mismo error que tenía el código viejo: shipping address, foto de perfil y descripción
vivían en la tabla `users` de auth, mezclado con credenciales. Separarlo evita que un cambio de
"quiero agregar la patente del auto" te obligue a tocar el servicio que emite tokens.

## Variables de entorno

Ver [`.env.example`](.env.example). Resumen:

| Variable | Descripción | Default |
|---|---|---|
| `DATABASE_URL` | Connection string de PostgreSQL | *(requerida)* |
| `JWT_SECRET` | Secreto para firmar los access tokens | `dev-secret-change-me` |
| `JWT_ALGORITHM` | Algoritmo JWT | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Duración del access token | `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Duración del refresh token | `30` |
| `BREVO_API_KEY` | API key de Brevo para envío de emails transaccionales | *(vacío = no envía, sólo loguea)* |
| `EMAIL_FROM` / `EMAIL_FROM_NAME` | Remitente de los emails | `no-reply@parklink.app` / `ParkLink` |
| `SKIP_EMAIL_VERIFICATION` | Si es `true`, no exige email verificado para loguear (dev/tests) | `false` |

## Cómo levantarlo

### Con Docker (recomendado)

```bash
cp .env.example .env    # completar JWT_SECRET y BREVO_API_KEY
docker compose up --build
```

Esto levanta Postgres (`db-auth`, puerto `5433`) y el servicio (puerto `8000`). Al iniciar,
`auth-service` corre `alembic upgrade head` automáticamente antes de levantar FastAPI.

### Local (sin Docker)

```bash
pip install -r requirements.txt
cp .env.example .env    # ajustar DATABASE_URL a tu Postgres local
python main.py
# o: uvicorn main:app --reload
```

## Tests

```bash
# con Docker (SQLite en memoria, no necesita Postgres levantado)
docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from auth-tests

# local
pip install -r requirements.txt
pytest
pytest -v                              # verbose
pytest --cov=app --cov-report=html     # cobertura (htmlcov/index.html)
```

> Nota: en este entorno no pude ejecutar `pytest` (sin `pip`/`venv` disponibles y sin acceso a
> Docker sin contraseña interactiva), así que corré la suite antes de dar por cerrado el cambio.
> El código pasó `python -m py_compile` sobre todos los módulos y una revisión manual línea por
> línea; aun así, correr los tests reales es el paso que falta para confirmar que todo funciona
> end-to-end.

Estructura:

```
tests/
├── conftest.py                # fixtures (DB SQLite de test, cliente, usuario de prueba)
├── test_security.py           # hashing de passwords, JWT, hashing de tokens opacos
└── api/
    ├── test_auth.py           # register, login, refresh, logout, sesiones, password reset
    └── test_user.py           # get/put/delete de perfil, control de acceso
```

## Estructura del proyecto

```
app/
├── api/            # routers FastAPI (auth.py, user.py) + dependencies (auth JWT)
├── models/         # SQLAlchemy: User, RefreshToken, VerificationToken
├── schemas/        # Pydantic: requests/responses
├── repositories/   # acceso a datos (users.py, tokens.py)
├── services/        # lógica de negocio (auth_service.py, users.py)
├── utils/          # email.py (Brevo), email_templates.py
├── config.py, database.py, security.py
alembic/            # migraciones (genera el esquema desde los modelos)
```
