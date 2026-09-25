from datetime import datetime, timedelta, timezone

from app.models import RegistrationVerification, UserStatus, VerificationToken, VerificationTokenType
from app.security import hash_password, hash_token
from app.services.auth_service import issue_email_verification_code

# -------------------------
# Helpers
# -------------------------


def _force_registration_code(db, verification_type: VerificationTokenType, target: str, code: str) -> RegistrationVerification:
    row = (
        db.query(RegistrationVerification)
        .filter(
            RegistrationVerification.type == verification_type,
            RegistrationVerification.target == target,
        )
        .order_by(RegistrationVerification.created_at.desc())
        .first()
    )
    row.token_hash = hash_token(code)
    db.commit()
    return row


def _verify_email_for_registration(client, db, email: str, code: str = "111111") -> None:
    request_response = client.post("/auth/registration/email/request", json={"email": email})
    assert request_response.status_code == 200
    _force_registration_code(db, VerificationTokenType.EMAIL, email, code)
    confirm_response = client.post(
        "/auth/registration/email/confirm", json={"email": email, "code": code}
    )
    assert confirm_response.status_code == 200


def _verify_phone_for_registration(client, db, phone: str, code: str = "222222") -> None:
    request_response = client.post("/auth/registration/phone/request", json={"phone": phone})
    assert request_response.status_code == 200
    _force_registration_code(db, VerificationTokenType.PHONE, phone, code)
    confirm_response = client.post(
        "/auth/registration/phone/confirm", json={"phone": phone, "code": code}
    )
    assert confirm_response.status_code == 200


def _register_verified_user(
    client,
    db,
    email="new@example.com",
    phone="+5491100000001",
    first_name="New",
    last_name="User",
    dni="20111222",
    birth_date="1990-01-01",
    password="SecurePass123",
):
    _verify_email_for_registration(client, db, email)
    _verify_phone_for_registration(client, db, phone)
    return client.post(
        "/auth/register",
        json={
            "email": email,
            "phone": phone,
            "first_name": first_name,
            "last_name": last_name,
            "dni": dni,
            "birth_date": birth_date,
            "password": password,
        },
    )


# -------------------------
# Registration wizard: email step
# -------------------------


def test_registration_email_request_and_confirm(client, db):
    _verify_email_for_registration(client, db, "wizard-email@example.com")


def test_registration_email_request_rejects_already_registered(client, test_user):
    response = client.post(
        "/auth/registration/email/request", json={"email": test_user.email}
    )
    assert response.status_code == 400


def test_registration_email_confirm_rejects_invalid_code(client):
    response = client.post(
        "/auth/registration/email/confirm",
        json={"email": "ghost@example.com", "code": "000000"},
    )
    assert response.status_code == 400


def test_registration_email_confirm_tracks_failed_attempts(client, db):
    email = "wizard-attempts@example.com"
    client.post("/auth/registration/email/request", json={"email": email})
    _force_registration_code(db, VerificationTokenType.EMAIL, email, "123456")

    wrong = client.post(
        "/auth/registration/email/confirm", json={"email": email, "code": "111111"}
    )
    assert wrong.status_code == 400
    assert "4 attempts remaining" in wrong.json()["detail"]

    right = client.post(
        "/auth/registration/email/confirm", json={"email": email, "code": "123456"}
    )
    assert right.status_code == 200


# -------------------------
# Registration wizard: phone step
# -------------------------


def test_registration_phone_request_and_confirm(client, db):
    _verify_phone_for_registration(client, db, "+5491100000002")


def test_registration_phone_request_rejects_already_registered(client, test_user):
    response = client.post(
        "/auth/registration/phone/request", json={"phone": test_user.phone}
    )
    assert response.status_code == 400


def test_registration_phone_confirm_rejects_invalid_code(client):
    response = client.post(
        "/auth/registration/phone/confirm",
        json={"phone": "+5491100000003", "code": "000000"},
    )
    assert response.status_code == 400


# -------------------------
# Register (final step)
# -------------------------


def test_register_creates_already_verified_user(client, db):
    response = _register_verified_user(client, db)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert body["phone"] == "+5491100000001"
    assert body["name"] == "New User"
    assert body["email_verified"] is True
    assert body["phone_verified"] is True
    assert body["status"] == "ACTIVE"


def test_register_rejects_without_email_verification(client, db):
    _verify_phone_for_registration(client, db, "+5491100000004")
    response = client.post(
        "/auth/register",
        json={
            "email": "noverify@example.com",
            "phone": "+5491100000004",
            "first_name": "Some",
            "last_name": "One",
            "dni": "20000004",
            "birth_date": "1990-01-01",
            "password": "SecurePass123",
        },
    )
    assert response.status_code == 400
    assert "Email" in response.json()["detail"]


def test_register_rejects_without_phone_verification(client, db):
    _verify_email_for_registration(client, db, "noverify2@example.com")
    response = client.post(
        "/auth/register",
        json={
            "email": "noverify2@example.com",
            "phone": "+5491100000005",
            "first_name": "Some",
            "last_name": "One",
            "dni": "20000005",
            "birth_date": "1990-01-01",
            "password": "SecurePass123",
        },
    )
    assert response.status_code == 400
    assert "Phone" in response.json()["detail"]


def test_register_rejects_duplicate_email(client, db, test_user):
    _verify_phone_for_registration(client, db, "+5491100000006")
    response = client.post(
        "/auth/register",
        json={
            "email": test_user.email,
            "phone": "+5491100000006",
            "first_name": "Some",
            "last_name": "One",
            "dni": "20000006",
            "birth_date": "1990-01-01",
            "password": "SecurePass123",
        },
    )
    assert response.status_code == 400


def test_register_rejects_duplicate_phone(client, db, test_user):
    _verify_email_for_registration(client, db, "dupphone@example.com")
    response = client.post(
        "/auth/register",
        json={
            "email": "dupphone@example.com",
            "phone": test_user.phone,
            "first_name": "Some",
            "last_name": "One",
            "dni": "20000007",
            "birth_date": "1990-01-01",
            "password": "SecurePass123",
        },
    )
    assert response.status_code == 400


def test_register_rejects_duplicate_dni(client, db, test_user):
    _verify_email_for_registration(client, db, "dupdni@example.com")
    _verify_phone_for_registration(client, db, "+5491100000010")
    response = client.post(
        "/auth/register",
        json={
            "email": "dupdni@example.com",
            "phone": "+5491100000010",
            "first_name": "Some",
            "last_name": "One",
            "dni": test_user.dni,
            "birth_date": "1990-01-01",
            "password": "SecurePass123",
        },
    )
    assert response.status_code == 400


def test_register_rejects_weak_password(client, db):
    _verify_email_for_registration(client, db, "weak@example.com")
    _verify_phone_for_registration(client, db, "+5491100000007")
    response = client.post(
        "/auth/register",
        json={
            "email": "weak@example.com",
            "phone": "+5491100000007",
            "first_name": "Some",
            "last_name": "One",
            "dni": "20000008",
            "birth_date": "1990-01-01",
            "password": "weak",
        },
    )
    assert response.status_code == 400


def test_register_rejects_underage(client, db):
    _verify_email_for_registration(client, db, "kid@example.com")
    _verify_phone_for_registration(client, db, "+5491100000008")
    recent_birth_date = (datetime.now(timezone.utc) - timedelta(days=365 * 10)).date().isoformat()
    response = client.post(
        "/auth/register",
        json={
            "email": "kid@example.com",
            "phone": "+5491100000008",
            "first_name": "Some",
            "last_name": "One",
            "dni": "20000009",
            "birth_date": recent_birth_date,
            "password": "SecurePass123",
        },
    )
    assert response.status_code == 400


# -------------------------
# Login / refresh / logout / sessions (unaffected by the wizard, using an
# already-verified test_user)
# -------------------------


def test_login_success_returns_token_pair(client, test_user):
    response = client.post(
        "/auth/login",
        json={"email": test_user.email, "password": "Password123", "device_id": "d1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


def test_login_rejects_wrong_password(client, test_user):
    response = client.post(
        "/auth/login",
        json={"email": test_user.email, "password": "WrongPassword1"},
    )
    assert response.status_code == 401


def test_login_blocks_unverified_email(client, db):
    # register() can no longer produce an unverified user through the public
    # API -- this exercises the login-side guard directly (defense in depth)
    # by creating one straight through the ORM.
    from app.models import User

    user = User(
        email="unverified@example.com",
        phone="+5491100000009",
        first_name="Some",
        last_name="One",
        password_hash=hash_password("SecurePass123"),
        email_verified=False,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    db.commit()

    response = client.post(
        "/auth/login",
        json={"email": "unverified@example.com", "password": "SecurePass123"},
    )
    assert response.status_code == 403


def test_refresh_rotates_token_and_invalidates_old_one(client, test_user):
    login_response = client.post(
        "/auth/login",
        json={"email": test_user.email, "password": "Password123", "device_id": "d1"},
    )
    old_refresh_token = login_response.json()["refresh_token"]

    refresh_response = client.post("/auth/refresh", json={"refresh_token": old_refresh_token})
    assert refresh_response.status_code == 200
    new_refresh_token = refresh_response.json()["refresh_token"]
    assert new_refresh_token != old_refresh_token

    reuse_response = client.post("/auth/refresh", json={"refresh_token": old_refresh_token})
    assert reuse_response.status_code == 401


def test_logout_revokes_refresh_token(client, test_user):
    login_response = client.post(
        "/auth/login",
        json={"email": test_user.email, "password": "Password123", "device_id": "d1"},
    )
    refresh_token = login_response.json()["refresh_token"]

    logout_response = client.post("/auth/logout", json={"refresh_token": refresh_token})
    assert logout_response.status_code == 200

    refresh_response = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_response.status_code == 401


def test_sessions_list_and_revoke(client, test_user):
    client.post(
        "/auth/login",
        json={"email": test_user.email, "password": "Password123", "device_id": "phone-1"},
    )
    login_2 = client.post(
        "/auth/login",
        json={"email": test_user.email, "password": "Password123", "device_id": "phone-2"},
    )
    access_token = login_2.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    sessions_response = client.get("/auth/sessions", headers=headers)
    assert sessions_response.status_code == 200
    sessions = sessions_response.json()
    assert len(sessions) == 2

    session_id = sessions[0]["id"]
    revoke_response = client.delete(f"/auth/sessions/{session_id}", headers=headers)
    assert revoke_response.status_code == 200

    sessions_after = client.get("/auth/sessions", headers=headers).json()
    assert len(sessions_after) == 1


# -------------------------
# Password reset (code-based, mirrors email/phone verification)
# -------------------------


def _force_latest_reset_code(db, user_id, code: str) -> VerificationToken:
    token_row = (
        db.query(VerificationToken)
        .filter(
            VerificationToken.user_id == user_id,
            VerificationToken.type == VerificationTokenType.PASSWORD_RESET,
        )
        .order_by(VerificationToken.created_at.desc())
        .first()
    )
    token_row.token_hash = hash_token(code)
    db.commit()
    return token_row


def test_password_reset_flow(client, test_user, db):
    request_response = client.post(
        "/auth/password-reset/request", json={"email": test_user.email}
    )
    assert request_response.status_code == 200
    _force_latest_reset_code(db, test_user.id, "123456")

    confirm_response = client.post(
        "/auth/password-reset/confirm",
        json={"email": test_user.email, "code": "123456", "new_password": "NewPassword123"},
    )
    assert confirm_response.status_code == 200

    login_response = client.post(
        "/auth/login",
        json={"email": test_user.email, "password": "NewPassword123"},
    )
    assert login_response.status_code == 200


def test_password_reset_confirm_rejects_invalid_code(client):
    response = client.post(
        "/auth/password-reset/confirm",
        json={"email": "ghost@example.com", "code": "000000", "new_password": "NewPassword123"},
    )
    assert response.status_code == 400


def test_password_reset_confirm_tracks_failed_attempts(client, test_user, db):
    client.post("/auth/password-reset/request", json={"email": test_user.email})
    _force_latest_reset_code(db, test_user.id, "123456")

    wrong = client.post(
        "/auth/password-reset/confirm",
        json={"email": test_user.email, "code": "111111", "new_password": "NewPassword123"},
    )
    assert wrong.status_code == 400
    assert "4 attempts remaining" in wrong.json()["detail"]

    right = client.post(
        "/auth/password-reset/confirm",
        json={"email": test_user.email, "code": "123456", "new_password": "NewPassword123"},
    )
    assert right.status_code == 200


# -------------------------
# Post-login email re-verification (resending a code to an unverified
# account's current address -- unrelated to changing to a new email, which
# is /users/{id}/email/*, covered in test_user.py).
# -------------------------


def _force_latest_email_code(db, user_id, code: str) -> VerificationToken:
    token_row = (
        db.query(VerificationToken)
        .filter(
            VerificationToken.user_id == user_id,
            VerificationToken.type == VerificationTokenType.EMAIL,
        )
        .order_by(VerificationToken.created_at.desc())
        .first()
    )
    token_row.token_hash = hash_token(code)
    db.commit()
    return token_row


def test_email_verification_confirm_tracks_failed_attempts(client, test_user, db):
    issue_email_verification_code(db, test_user)
    _force_latest_email_code(db, test_user.id, "123456")

    wrong = client.post(
        "/auth/email-verification/confirm",
        json={"email": test_user.email, "code": "111111"},
    )
    assert wrong.status_code == 400
    assert "4 attempts remaining" in wrong.json()["detail"]

    right = client.post(
        "/auth/email-verification/confirm",
        json={"email": test_user.email, "code": "123456"},
    )
    assert right.status_code == 200


def test_email_verification_confirm_locks_after_max_attempts(client, test_user, db):
    # request_email_verification() (used for the resend below) only issues a
    # code for a not-yet-verified user -- put test_user in that state, as if
    # they'd just changed to an email they haven't confirmed yet.
    test_user.email_verified = False
    db.add(test_user)
    db.commit()

    issue_email_verification_code(db, test_user)
    _force_latest_email_code(db, test_user.id, "123456")

    for _ in range(5):
        client.post(
            "/auth/email-verification/confirm",
            json={"email": test_user.email, "code": "111111"},
        )

    response = client.post(
        "/auth/email-verification/confirm",
        json={"email": test_user.email, "code": "123456"},
    )
    assert response.status_code == 400

    burned = (
        db.query(VerificationToken)
        .filter(
            VerificationToken.user_id == test_user.id,
            VerificationToken.type == VerificationTokenType.EMAIL,
        )
        .order_by(VerificationToken.created_at.desc())
        .first()
    )
    burned.created_at = datetime.now(timezone.utc) - timedelta(seconds=61)
    db.commit()

    resend = client.post(
        "/auth/email-verification/request", json={"email": test_user.email}
    )
    assert resend.status_code == 200
    _force_latest_email_code(db, test_user.id, "654321")

    confirm_response = client.post(
        "/auth/email-verification/confirm",
        json={"email": test_user.email, "code": "654321"},
    )
    assert confirm_response.status_code == 200


def test_email_verification_confirm_rejects_invalid_code(client):
    response = client.post(
        "/auth/email-verification/confirm",
        json={"email": "ghost@example.com", "code": "000000"},
    )
    assert response.status_code == 400


def test_email_verification_request_is_generic_for_unknown_email(client):
    response = client.post(
        "/auth/email-verification/request", json={"email": "ghost@example.com"}
    )
    assert response.status_code == 200
