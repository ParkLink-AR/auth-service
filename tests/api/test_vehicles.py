import uuid
from datetime import date

from app.models import User
from app.security import hash_password


def _login(client, test_user):
    response = client.post(
        "/auth/login",
        json={"email": test_user.email, "password": "Password123", "device_id": "d1"},
    )
    return response.json()["access_token"]


def _other_user(db, **overrides):
    defaults = dict(
        email="vehicles-other@example.com",
        phone="+5491100007788",
        first_name="Other",
        last_name="User",
        dni="30777888",
        birth_date=date(1990, 1, 1),
        password_hash=hash_password("Password123"),
        email_verified=True,
        phone_verified=True,
    )
    defaults.update(overrides)
    other = User(**defaults)
    db.add(other)
    db.commit()
    db.refresh(other)
    return other


def test_list_vehicles_defaults_to_empty(client, test_user):
    token = _login(client, test_user)
    response = client.get(
        f"/users/{test_user.id}/vehicles", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json() == []


def test_list_vehicles_requires_auth(client, test_user):
    response = client.get(f"/users/{test_user.id}/vehicles")
    assert response.status_code == 401


def test_list_another_users_vehicles_is_forbidden(client, test_user):
    token = _login(client, test_user)
    response = client.get(
        f"/users/{uuid.uuid4()}/vehicles", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403


def test_create_vehicle_uppercases_plate_and_country(client, test_user):
    token = _login(client, test_user)
    response = client.post(
        f"/users/{test_user.id}/vehicles",
        json={"plate": "ab123cd", "brand": "Toyota", "model": "Corolla", "country": "ar"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["plate"] == "AB123CD"
    assert body["brand"] == "Toyota"
    assert body["model"] == "Corolla"
    assert body["country"] == "AR"
    assert "id" in body


def test_create_vehicle_rejects_unsupported_country(client, test_user):
    token = _login(client, test_user)
    response = client.post(
        f"/users/{test_user.id}/vehicles",
        json={"plate": "AB123CD", "brand": "Toyota", "model": "Corolla", "country": "US"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


def test_create_vehicle_accepts_old_format_argentine_plate(client, test_user):
    token = _login(client, test_user)
    response = client.post(
        f"/users/{test_user.id}/vehicles",
        json={"plate": "abc123", "brand": "Ford", "model": "Falcon", "country": "AR"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert response.json()["plate"] == "ABC123"


def test_create_vehicle_accepts_mercosur_format_argentine_plate(client, test_user):
    token = _login(client, test_user)
    response = client.post(
        f"/users/{test_user.id}/vehicles",
        json={"plate": "ab123cd", "brand": "Toyota", "model": "Corolla", "country": "AR"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert response.json()["plate"] == "AB123CD"


def test_create_vehicle_accepts_old_format_argentine_moto_plate(client, test_user):
    token = _login(client, test_user)
    response = client.post(
        f"/users/{test_user.id}/vehicles",
        json={"plate": "123abc", "brand": "Honda", "model": "Wave", "country": "AR"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert response.json()["plate"] == "123ABC"


def test_create_vehicle_accepts_mercosur_format_argentine_moto_plate(client, test_user):
    token = _login(client, test_user)
    response = client.post(
        f"/users/{test_user.id}/vehicles",
        json={"plate": "a123abc", "brand": "Honda", "model": "Wave", "country": "AR"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert response.json()["plate"] == "A123ABC"


def test_create_vehicle_rejects_argentine_plate_matching_neither_format(client, test_user):
    token = _login(client, test_user)
    response = client.post(
        f"/users/{test_user.id}/vehicles",
        # 4 letters + 2 digits -- not the old ABC123 shape nor the Mercosur AB123CD one.
        json={"plate": "ABCD12", "brand": "Toyota", "model": "Corolla", "country": "AR"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


def test_create_vehicle_rejects_country_other_than_argentina(client, test_user):
    token = _login(client, test_user)
    response = client.post(
        f"/users/{test_user.id}/vehicles",
        # Only Argentina is supported for now -- see schemas.VEHICLE_COUNTRIES.
        json={"plate": "ABC1D23", "brand": "Fiat", "model": "Uno", "country": "BR"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


def test_create_vehicle_rejects_empty_brand(client, test_user):
    token = _login(client, test_user)
    response = client.post(
        f"/users/{test_user.id}/vehicles",
        json={"plate": "AB123CD", "brand": "   ", "model": "Corolla", "country": "AR"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


def test_create_vehicle_requires_self(client, test_user, db):
    other = _other_user(db)
    token = _login(client, test_user)
    response = client.post(
        f"/users/{other.id}/vehicles",
        json={"plate": "AB123CD", "brand": "Toyota", "model": "Corolla", "country": "AR"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_list_vehicles_returns_created_ones_oldest_first(client, test_user):
    token = _login(client, test_user)
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        f"/users/{test_user.id}/vehicles",
        json={"plate": "AB123CD", "brand": "Toyota", "model": "Corolla", "country": "AR"},
        headers=headers,
    )
    client.post(
        f"/users/{test_user.id}/vehicles",
        json={"plate": "XY987ZW", "brand": "Ford", "model": "Fiesta", "country": "AR"},
        headers=headers,
    )

    response = client.get(f"/users/{test_user.id}/vehicles", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["plate"] == "AB123CD"
    assert body[1]["plate"] == "XY987ZW"


def test_delete_vehicle_removes_it(client, test_user):
    token = _login(client, test_user)
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        f"/users/{test_user.id}/vehicles",
        json={"plate": "AB123CD", "brand": "Toyota", "model": "Corolla", "country": "AR"},
        headers=headers,
    ).json()

    response = client.delete(f"/users/{test_user.id}/vehicles/{created['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"deleted": True}

    list_response = client.get(f"/users/{test_user.id}/vehicles", headers=headers)
    assert list_response.json() == []


def test_delete_unknown_vehicle_is_not_found(client, test_user):
    token = _login(client, test_user)
    response = client.delete(
        f"/users/{test_user.id}/vehicles/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_delete_vehicle_requires_self(client, test_user, db):
    other = _other_user(db)
    token_other = _login(client, other)
    created = client.post(
        f"/users/{other.id}/vehicles",
        json={"plate": "AB123CD", "brand": "Toyota", "model": "Corolla", "country": "AR"},
        headers={"Authorization": f"Bearer {token_other}"},
    ).json()

    token = _login(client, test_user)
    response = client.delete(
        f"/users/{other.id}/vehicles/{created['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
