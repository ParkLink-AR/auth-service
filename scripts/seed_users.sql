-- Seed test accounts for local development.
-- Passwords are hashed with pbkdf2_sha256 (29 000 rounds).
--
-- Account                      | Password
-- -----------------------------|----------------
-- conductor@parklink.com       | Conductor1!
-- propietario@parklink.com     | Propietario1!
-- admin@parklink.com           | Admin1!
--
-- Run once after `make up` (or after `make clean && make up`):
--
--   docker exec -i pll-db-auth-1 psql \
--       -U parklink_auth -d parklink_auth_db \
--       < auth-service/scripts/seed_users.sql

INSERT INTO users (
    id, email, first_name, last_name,
    password_hash, email_verified, phone_verified, status
)
VALUES
    (
        gen_random_uuid(),
        'conductor@parklink.com',
        'Carlos', 'Rodriguez',
        '$pbkdf2-sha256$29000$RwgBAMB4zxkjRGjNGSMkZA$AxsSV0iRPCM/ORbhPXQSwLAjwu4kfH6DjUbKxzXz1L0',
        true, false, 'ACTIVE'
    ),
    (
        gen_random_uuid(),
        'propietario@parklink.com',
        'Laura', 'Gomez',
        '$pbkdf2-sha256$29000$ZuydU8oZw5jzfm.N0TqnlA$dQFbvDrZRuKU3QBYfJGnADlgWy.i2cSFLJ2vIUx4bTY',
        true, false, 'ACTIVE'
    ),
    (
        gen_random_uuid(),
        'admin@parklink.com',
        'Admin', 'ParkLink',
        '$pbkdf2-sha256$29000$/T9n7N3bO6e01tqb0zrnvA$6bsdehZMfw/.7PVJIgKwVwqnvlY3/hg9ulvwergmT/M',
        true, false, 'ACTIVE'
    )
ON CONFLICT (email) DO NOTHING;
