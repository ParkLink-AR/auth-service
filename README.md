# auth-service

Microservicio de autenticación y gestión de usuarios de ParkLink. Maneja registro, login/logout con JWT, roles y permisos (conductor/propietario), y recuperación de contraseña.

auth-service: registro, login, tokens, permisos/roles, etc

POST /auth/register: Registrar un nuevo usuario en el sistema.

POST /auth/login: Autenticar credenciales y devolver el token JWT.

POST /auth/logout: Invalidar el token de la sesión actual.

GET /users/{id}: Obtener los datos del perfil del usuario

PUT /users/{id}: Actualizar la información personal de un usuario

POST /auth/password-reset/request: Solicitar el reseteo de contraseña (recibe el email, genera un token temporal).

POST /auth/password-reset/confirm: Confirmar el reseteo con el token recibido y la nueva contraseña.
