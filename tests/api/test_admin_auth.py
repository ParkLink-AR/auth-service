from jose import jwt

from app.config import settings
from app.models import AdminAccount, AdminRole
from app.security import hash_password
from main import _seed_first_superadmin

# The admin identity system (AdminAccount) is deliberately separate from the
# `users` table -- see app/models/admin_account.py and
# app/services/admin_auth.py. POST /admin/auth/login has no gateway gate (it
# IS the login); the /admin/accounts endpoints ARE gated by the gateway on
# `role: admin` like every other /admin/* route, but additionally do their
# own superadmin-only check inside the service via X-User-Id, which these
# tests set directly (the gateway injects it in real traffic).


def _make_admin(db, **overrides):
    defaults = dict(
        username="admin-default",
        password_hash=hash_password("AdminPass123"),
        role=AdminRole.ADMIN,
        is_active=True,
    )
    defaults.update(overrides)
    admin_account = AdminAccount(**defaults)
    db.add(admin_account)
    db.commit()
    db.refresh(admin_account)
    return admin_account


def _decode(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


# -------------------------
# Login
# -------------------------


def test_admin_login_success(client, db):
    _make_admin(db, username="root-login-ok", password_hash=hash_password("SuperSecret123"), role=AdminRole.SUPERADMIN)

    response = client.post(
        "/admin/auth/login", json={"username": "root-login-ok", "password": "SuperSecret123"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    assert "refresh_token" not in body


def test_admin_login_rejects_wrong_password(client, db):
    _make_admin(db, username="root-login-wrong", password_hash=hash_password("SuperSecret123"))

    response = client.post(
        "/admin/auth/login", json={"username": "root-login-wrong", "password": "NotIt123"}
    )
    assert response.status_code == 401


def test_admin_login_rejects_unknown_username(client):
    response = client.post(
        "/admin/auth/login", json={"username": "nobody-like-this", "password": "whatever123"}
    )
    assert response.status_code == 401


def test_admin_login_rejects_inactive_account(client, db):
    _make_admin(
        db,
        username="root-login-inactive",
        password_hash=hash_password("SuperSecret123"),
        is_active=False,
    )

    response = client.post(
        "/admin/auth/login", json={"username": "root-login-inactive", "password": "SuperSecret123"}
    )
    assert response.status_code == 403


def test_admin_login_jwt_claims(client, db):
    _make_admin(
        db,
        username="root-login-claims",
        password_hash=hash_password("SuperSecret123"),
        role=AdminRole.SUPERADMIN,
    )

    response = client.post(
        "/admin/auth/login", json={"username": "root-login-claims", "password": "SuperSecret123"}
    )
    assert response.status_code == 200
    payload = _decode(response.json()["access_token"])
    assert payload["role"] == "admin"
    assert payload["admin_role"] == "SUPERADMIN"
    assert payload["admin_username"] == "root-login-claims"


# -------------------------
# POST /admin/accounts
# -------------------------


def test_create_admin_account_succeeds_for_superadmin(client, db):
    superadmin = _make_admin(db, username="root-create-ok", role=AdminRole.SUPERADMIN)

    response = client.post(
        "/admin/accounts",
        json={"username": "brand-new-admin", "password": "NewAdminPass123", "role": "ADMIN"},
        headers={"X-User-Id": str(superadmin.id)},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "brand-new-admin"
    assert body["role"] == "ADMIN"
    assert body["is_active"] is True
    assert "password" not in body
    assert "password_hash" not in body


def test_create_admin_account_403_for_non_superadmin_caller(client, db):
    regular_admin = _make_admin(db, username="just-an-admin", role=AdminRole.ADMIN)

    response = client.post(
        "/admin/accounts",
        json={"username": "should-not-exist", "password": "NewAdminPass123", "role": "ADMIN"},
        headers={"X-User-Id": str(regular_admin.id)},
    )
    assert response.status_code == 403


def test_create_admin_account_403_when_caller_missing(client):
    response = client.post(
        "/admin/accounts",
        json={"username": "no-caller-id", "password": "NewAdminPass123", "role": "ADMIN"},
    )
    assert response.status_code == 403


def test_create_admin_account_400_on_duplicate_username(client, db):
    superadmin = _make_admin(db, username="root-create-dupe", role=AdminRole.SUPERADMIN)

    first = client.post(
        "/admin/accounts",
        json={"username": "dupe-admin", "password": "NewAdminPass123", "role": "ADMIN"},
        headers={"X-User-Id": str(superadmin.id)},
    )
    assert first.status_code == 201

    second = client.post(
        "/admin/accounts",
        json={"username": "dupe-admin", "password": "AnotherPass123", "role": "ADMIN"},
        headers={"X-User-Id": str(superadmin.id)},
    )
    assert second.status_code == 400


# -------------------------
# GET /admin/accounts
# -------------------------


def test_list_admin_accounts_for_superadmin(client, db):
    superadmin = _make_admin(db, username="root-list-ok", role=AdminRole.SUPERADMIN)
    _make_admin(db, username="listed-admin", role=AdminRole.ADMIN)

    response = client.get("/admin/accounts", headers={"X-User-Id": str(superadmin.id)})
    assert response.status_code == 200
    usernames = {row["username"] for row in response.json()}
    assert "root-list-ok" in usernames
    assert "listed-admin" in usernames


def test_list_admin_accounts_403_for_non_superadmin_caller(client, db):
    regular_admin = _make_admin(db, username="just-an-admin-2", role=AdminRole.ADMIN)

    response = client.get("/admin/accounts", headers={"X-User-Id": str(regular_admin.id)})
    assert response.status_code == 403


# -------------------------
# PATCH /admin/accounts/{id}
# -------------------------


def test_patch_admin_account_toggles_active(client, db):
    superadmin = _make_admin(db, username="root-patch-ok", role=AdminRole.SUPERADMIN)
    target = _make_admin(db, username="toggle-target", role=AdminRole.ADMIN)

    response = client.patch(
        f"/admin/accounts/{target.id}",
        json={"is_active": False},
        headers={"X-User-Id": str(superadmin.id)},
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False


def test_patch_admin_account_403_for_non_superadmin_caller(client, db):
    regular_admin = _make_admin(db, username="just-an-admin-3", role=AdminRole.ADMIN)
    target = _make_admin(db, username="toggle-target-2", role=AdminRole.ADMIN)

    response = client.patch(
        f"/admin/accounts/{target.id}",
        json={"is_active": False},
        headers={"X-User-Id": str(regular_admin.id)},
    )
    assert response.status_code == 403


def test_patch_admin_account_rejects_self_deactivation(client, db):
    superadmin = _make_admin(db, username="root-patch-self", role=AdminRole.SUPERADMIN)

    response = client.patch(
        f"/admin/accounts/{superadmin.id}",
        json={"is_active": False},
        headers={"X-User-Id": str(superadmin.id)},
    )
    assert response.status_code == 400


# -------------------------
# Password change (superadmin-only)
# -------------------------


def test_set_admin_password_changes_password_and_allows_login(client, db):
    superadmin = _make_admin(db, username="root-pw-ok", role=AdminRole.SUPERADMIN)
    target = _make_admin(db, username="pw-target", role=AdminRole.ADMIN)

    response = client.post(
        f"/admin/accounts/{target.id}/password",
        json={"new_password": "BrandNewPass123"},
        headers={"X-User-Id": str(superadmin.id)},
    )
    assert response.status_code == 200
    assert response.json()["id"] == str(target.id)

    login = client.post(
        "/admin/auth/login", json={"username": "pw-target", "password": "BrandNewPass123"}
    )
    assert login.status_code == 200


def test_set_admin_password_403_for_non_superadmin_caller(client, db):
    regular_admin = _make_admin(db, username="just-an-admin-4", role=AdminRole.ADMIN)
    target = _make_admin(db, username="pw-target-2", role=AdminRole.ADMIN)

    response = client.post(
        f"/admin/accounts/{target.id}/password",
        json={"new_password": "BrandNewPass123"},
        headers={"X-User-Id": str(regular_admin.id)},
    )
    assert response.status_code == 403


def test_set_admin_password_404_for_unknown_target(client, db):
    superadmin = _make_admin(db, username="root-pw-404", role=AdminRole.SUPERADMIN)

    response = client.post(
        "/admin/accounts/99999999-9999-9999-9999-999999999999/password",
        json={"new_password": "BrandNewPass123"},
        headers={"X-User-Id": str(superadmin.id)},
    )
    assert response.status_code == 404


def test_set_admin_password_rejects_weak_password(client, db):
    superadmin = _make_admin(db, username="root-pw-weak", role=AdminRole.SUPERADMIN)
    target = _make_admin(db, username="pw-target-3", role=AdminRole.ADMIN)

    response = client.post(
        f"/admin/accounts/{target.id}/password",
        json={"new_password": "short"},
        headers={"X-User-Id": str(superadmin.id)},
    )
    # This repo's validation_exception_handler (main.py) rewrites FastAPI's default 422
    # into a 400 problem+json body -- see AdminAccountCreate's password tests for the
    # same convention.
    assert response.status_code == 400


# -------------------------
# Startup seed
# -------------------------


def test_seed_creates_exactly_one_superadmin(db):
    assert db.query(AdminAccount).count() == 0

    _seed_first_superadmin()

    accounts = db.query(AdminAccount).all()
    assert len(accounts) == 1
    assert accounts[0].username == "superadmin"
    assert accounts[0].role == AdminRole.SUPERADMIN


def test_seed_is_idempotent(db):
    _seed_first_superadmin()
    _seed_first_superadmin()
    _seed_first_superadmin()

    assert db.query(AdminAccount).count() == 1
