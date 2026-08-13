import uuid


def _login(client, test_user):
    response = client.post(
        "/auth/login",
        json={"email": test_user.email, "password": "Password123", "device_id": "d1"},
    )
    return response.json()["access_token"]


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


def test_update_phone(client, test_user):
    token = _login(client, test_user)
    response = client.put(
        f"/users/{test_user.id}",
        json={"phone": "+541199998888"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["phone"] == "+541199998888"
    assert response.json()["phone_verified"] is False


def test_update_email_requires_reverification(client, test_user):
    token = _login(client, test_user)
    response = client.put(
        f"/users/{test_user.id}",
        json={"email": "changed@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "changed@example.com"
    assert body["email_verified"] is False


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
