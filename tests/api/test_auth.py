from app.models import VerificationToken, VerificationTokenType
from app.security import hash_token


def test_register_creates_unverified_user(client, db):
    response = client.post(
        "/auth/register",
        json={"email": "new@example.com", "password": "SecurePass123"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert body["email_verified"] is False
    assert body["status"] == "ACTIVE"


def test_register_rejects_duplicate_email(client, test_user):
    response = client.post(
        "/auth/register",
        json={"email": test_user.email, "password": "SecurePass123"},
    )
    assert response.status_code == 400


def test_register_rejects_weak_password(client):
    response = client.post(
        "/auth/register",
        json={"email": "weak@example.com", "password": "weak"},
    )
    assert response.status_code == 400


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
    client.post(
        "/auth/register",
        json={"email": "unverified@example.com", "password": "SecurePass123"},
    )
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


def test_password_reset_flow(client, test_user, db):
    request_response = client.post(
        "/auth/password-reset/request", json={"email": test_user.email}
    )
    assert request_response.status_code == 200

    token_row = (
        db.query(VerificationToken)
        .filter(
            VerificationToken.user_id == test_user.id,
            VerificationToken.type == VerificationTokenType.PASSWORD_RESET,
        )
        .first()
    )
    # The raw token was only ever sent over email; reconstruct it isn't possible,
    # so we look it up by re-hashing candidate values is not feasible here.
    # Instead we simulate confirm via a fresh token generated the same way the
    # service does, to validate the confirm endpoint's contract end-to-end.
    from app.security import generate_opaque_token

    raw_token = generate_opaque_token()
    token_row.token_hash = hash_token(raw_token)
    db.commit()

    confirm_response = client.post(
        "/auth/password-reset/confirm",
        json={"token": raw_token, "new_password": "NewPassword123"},
    )
    assert confirm_response.status_code == 200

    login_response = client.post(
        "/auth/login",
        json={"email": test_user.email, "password": "NewPassword123"},
    )
    assert login_response.status_code == 200


def test_password_reset_confirm_rejects_invalid_token(client):
    response = client.post(
        "/auth/password-reset/confirm",
        json={"token": "not-a-real-token", "new_password": "NewPassword123"},
    )
    assert response.status_code == 400


def test_email_verification_flow(client, db):
    register_response = client.post(
        "/auth/register",
        json={"email": "toverify@example.com", "password": "SecurePass123"},
    )
    user_id = register_response.json()["id"]

    token_row = (
        db.query(VerificationToken)
        .filter(
            VerificationToken.user_id == user_id,
            VerificationToken.type == VerificationTokenType.EMAIL,
        )
        .order_by(VerificationToken.created_at.desc())
        .first()
    )

    from app.security import generate_opaque_token

    raw_token = generate_opaque_token()
    token_row.token_hash = hash_token(raw_token)
    db.commit()

    confirm_response = client.post(
        "/auth/email-verification/confirm", json={"token": raw_token}
    )
    assert confirm_response.status_code == 200

    login_response = client.post(
        "/auth/login",
        json={"email": "toverify@example.com", "password": "SecurePass123"},
    )
    assert login_response.status_code == 200


def test_email_verification_confirm_rejects_invalid_token(client):
    response = client.post(
        "/auth/email-verification/confirm", json={"token": "not-a-real-token"}
    )
    assert response.status_code == 400


def test_email_verification_request_is_generic_for_unknown_email(client):
    response = client.post(
        "/auth/email-verification/request", json={"email": "ghost@example.com"}
    )
    assert response.status_code == 200
