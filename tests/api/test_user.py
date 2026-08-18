import uuid
from datetime import date

from app.models import User, VerificationToken, VerificationTokenType
from app.security import hash_password, hash_token


def _login(client, test_user):
    response = client.post(
        "/auth/login",
        json={"email": test_user.email, "password": "Password123", "device_id": "d1"},
    )
    return response.json()["access_token"]


def _force_latest_code(db, user_id, token_type: VerificationTokenType, code: str) -> VerificationToken:
    token_row = (
        db.query(VerificationToken)
        .filter(VerificationToken.user_id == user_id, VerificationToken.type == token_type)
        .order_by(VerificationToken.created_at.desc())
        .first()
    )
    token_row.token_hash = hash_token(code)
    db.commit()
    return token_row


def test_get_own_profile(client, test_user):
    token = _login(client, test_user)
    response = client.get(
        f"/users/{test_user.id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == test_user.email


def test_get_profile_requires_auth(client, test_user):
    response = client.get(f"/users/{test_user.id}")
    assert response.status_code == 401


def test_get_another_users_profile_is_forbidden(client, test_user):
    token = _login(client, test_user)
    response = client.get(
        f"/users/{uuid.uuid4()}", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403


def test_update_profile_does_not_accept_email_or_phone(client, test_user):
    # first_name/last_name go through PUT /users/{id}; email/phone must go
    # through their own request/confirm endpoints (see tests below), so a
    # combined payload should just be ignored for those two fields.
    token = _login(client, test_user)
    response = client.put(
        f"/users/{test_user.id}",
        json={"first_name": "Updated", "email": "sneaky@example.com", "phone": "+541199998888"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["first_name"] == "Updated"
    assert body["email"] == test_user.email
    assert body["phone"] == test_user.phone


def test_email_change_flow(client, test_user, db):
    token = _login(client, test_user)
    headers = {"Authorization": f"Bearer {token}"}

    request_response = client.post(
        f"/users/{test_user.id}/email",
        json={"new_email": "changed@example.com"},
        headers=headers,
    )
    assert request_response.status_code == 200

    # Email is untouched until the code is confirmed.
    profile = client.get(f"/users/{test_user.id}", headers=headers).json()
    assert profile["email"] == test_user.email

    _force_latest_code(db, test_user.id, VerificationTokenType.EMAIL_CHANGE, "123456")
    confirm_response = client.post(
        f"/users/{test_user.id}/email/confirm", json={"code": "123456"}, headers=headers
    )
    assert confirm_response.status_code == 200
    body = confirm_response.json()
    assert body["email"] == "changed@example.com"
    assert body["email_verified"] is True


def test_email_change_confirm_rejects_wrong_code(client, test_user, db):
    token = _login(client, test_user)
    headers = {"Authorization": f"Bearer {token}"}

    client.post(f"/users/{test_user.id}/email", json={"new_email": "changed@example.com"}, headers=headers)
    _force_latest_code(db, test_user.id, VerificationTokenType.EMAIL_CHANGE, "123456")

    response = client.post(f"/users/{test_user.id}/email/confirm", json={"code": "000000"}, headers=headers)
    assert response.status_code == 400

    profile = client.get(f"/users/{test_user.id}", headers=headers).json()
    assert profile["email"] == test_user.email


def test_email_change_rejects_already_registered_email(client, test_user, db):
    other = User(
        email="taken@example.com",
        phone="+5491100000077",
        first_name="Other",
        last_name="User",
        dni="30777888",
        birth_date=date(1990, 1, 1),
        password_hash=hash_password("Password123"),
        email_verified=True,
        phone_verified=True,
    )
    db.add(other)
    db.commit()

    token = _login(client, test_user)
    response = client.post(
        f"/users/{test_user.id}/email",
        json={"new_email": "taken@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


def test_phone_change_flow(client, test_user, db):
    token = _login(client, test_user)
    headers = {"Authorization": f"Bearer {token}"}

    request_response = client.post(
        f"/users/{test_user.id}/phone",
        json={"new_phone": "+5491199998888"},
        headers=headers,
    )
    assert request_response.status_code == 200

    profile = client.get(f"/users/{test_user.id}", headers=headers).json()
    assert profile["phone"] == test_user.phone

    _force_latest_code(db, test_user.id, VerificationTokenType.PHONE_CHANGE, "654321")
    confirm_response = client.post(
        f"/users/{test_user.id}/phone/confirm", json={"code": "654321"}, headers=headers
    )
    assert confirm_response.status_code == 200
    body = confirm_response.json()
    assert body["phone"] == "+5491199998888"
    assert body["phone_verified"] is True


def test_phone_change_confirm_tracks_failed_attempts(client, test_user, db):
    token = _login(client, test_user)
    headers = {"Authorization": f"Bearer {token}"}

    client.post(f"/users/{test_user.id}/phone", json={"new_phone": "+5491199998888"}, headers=headers)
    _force_latest_code(db, test_user.id, VerificationTokenType.PHONE_CHANGE, "654321")

    wrong = client.post(f"/users/{test_user.id}/phone/confirm", json={"code": "111111"}, headers=headers)
    assert wrong.status_code == 400
    assert "4 attempts remaining" in wrong.json()["detail"]

    right = client.post(f"/users/{test_user.id}/phone/confirm", json={"code": "654321"}, headers=headers)
    assert right.status_code == 200


def test_delete_account_requires_correct_password(client, test_user):
    token = _login(client, test_user)
    response = client.request(
        "DELETE",
        f"/users/{test_user.id}",
        json={"password": "WrongPassword1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_delete_account_soft_deletes_and_revokes_sessions(client, test_user):
    token = _login(client, test_user)
    response = client.request(
        "DELETE",
        f"/users/{test_user.id}",
        json={"password": "Password123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200

    # The access token still decodes, but the dependency must reject non-ACTIVE users.
    profile_response = client.get(
        f"/users/{test_user.id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert profile_response.status_code == 403

    login_response = client.post(
        "/auth/login", json={"email": test_user.email, "password": "Password123"}
    )
    assert login_response.status_code == 401
