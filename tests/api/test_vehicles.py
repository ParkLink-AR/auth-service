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
        json={"type": "car", "plate": "ab123cd", "brand": "Toyota", "model": "Corolla", "country": "ar"},
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
        json={"type": "car", "plate": "AB123CD", "brand": "Toyota", "model": "Corolla", "country": "US"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


def test_create_vehicle_accepts_old_format_argentine_plate(client, test_user):
    token = _login(client, test_user)
    response = client.post(
        f"/users/{test_user.id}/vehicles",
        json={"type": "car", "plate": "abc123", "brand": "Ford", "model": "Falcon", "country": "AR"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert response.json()["plate"] == "ABC123"


def test_create_vehicle_accepts_mercosur_format_argentine_plate(client, test_user):
    token = _login(client, test_user)
    response = client.post(
        f"/users/{test_user.id}/vehicles",
        json={"type": "car", "plate": "ab123cd", "brand": "Toyota", "model": "Corolla", "country": "AR"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert response.json()["plate"] == "AB123CD"


def test_create_vehicle_accepts_old_format_argentine_moto_plate(client, test_user):
    token = _login(client, test_user)
    response = client.post(
        f"/users/{test_user.id}/vehicles",
        json={"type": "car", "plate": "123abc", "brand": "Honda", "model": "Wave", "country": "AR"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert response.json()["plate"] == "123ABC"


def test_create_vehicle_accepts_mercosur_format_argentine_moto_plate(client, test_user):
    token = _login(client, test_user)
    response = client.post(
        f"/users/{test_user.id}/vehicles",
        json={"type": "car", "plate": "a123abc", "brand": "Honda", "model": "Wave", "country": "AR"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert response.json()["plate"] == "A123ABC"


def test_create_vehicle_rejects_argentine_plate_matching_neither_format(client, test_user):
    token = _login(client, test_user)
    response = client.post(
        f"/users/{test_user.id}/vehicles",
        # 4 letters + 2 digits -- not the old ABC123 shape nor the Mercosur AB123CD one.
        json={"type": "car", "plate": "ABCD12", "brand": "Toyota", "model": "Corolla", "country": "AR"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


def test_create_vehicle_rejects_country_other_than_argentina(client, test_user):
    token = _login(client, test_user)
    response = client.post(
        f"/users/{test_user.id}/vehicles",
        # Only Argentina is supported for now -- see schemas.VEHICLE_COUNTRIES.
        json={"type": "car", "plate": "ABC1D23", "brand": "Fiat", "model": "Uno", "country": "BR"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


def test_create_vehicle_rejects_empty_brand(client, test_user):
    token = _login(client, test_user)
    response = client.post(
        f"/users/{test_user.id}/vehicles",
        json={"type": "car", "plate": "AB123CD", "brand": "   ", "model": "Corolla", "country": "AR"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


def test_create_vehicle_requires_self(client, test_user, db):
    other = _other_user(db)
    token = _login(client, test_user)
    response = client.post(
        f"/users/{other.id}/vehicles",
        json={"type": "car", "plate": "AB123CD", "brand": "Toyota", "model": "Corolla", "country": "AR"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_list_vehicles_returns_created_ones_oldest_first(client, test_user):
    token = _login(client, test_user)
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        f"/users/{test_user.id}/vehicles",
        json={"type": "car", "plate": "AB123CD", "brand": "Toyota", "model": "Corolla", "country": "AR"},
        headers=headers,
    )
    client.post(
        f"/users/{test_user.id}/vehicles",
        json={"type": "car", "plate": "XY987ZW", "brand": "Ford", "model": "Fiesta", "country": "AR"},
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
        json={"type": "car", "plate": "AB123CD", "brand": "Toyota", "model": "Corolla", "country": "AR"},
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
        json={"type": "car", "plate": "AB123CD", "brand": "Toyota", "model": "Corolla", "country": "AR"},
        headers={"Authorization": f"Bearer {token_other}"},
    ).json()

    token = _login(client, test_user)
    response = client.delete(
        f"/users/{other.id}/vehicles/{created['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_create_vehicle_normalizes_plate_and_capitalizes_names(client, test_user):
    token = _login(client, test_user)
    response = client.post(
        f"/users/{test_user.id}/vehicles",
        json={"type": "car", "plate": " ab 123-cd ", "brand": "honda", "model": "xr 250  tornado", "country": "ar"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["plate"] == "AB123CD"
    assert body["brand"] == "Honda"
    assert body["model"] == "Xr 250 Tornado"


def test_create_vehicle_keeps_existing_capitals(client, test_user):
    token = _login(client, test_user)
    response = client.post(
        f"/users/{test_user.id}/vehicles",
        json={"type": "car", "plate": "a123bcd", "brand": "BMW", "model": "XR 250", "country": "AR"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["brand"] == "BMW"
    assert body["model"] == "XR 250"


def _create(client, test_user, token, payload):
    return client.post(
        f"/users/{test_user.id}/vehicles", json=payload, headers={"Authorization": f"Bearer {token}"}
    )


def test_create_vehicle_saves_its_type(client, test_user):
    token = _login(client, test_user)
    response = _create(
        client, test_user, token,
        {"type": "Van", "plate": "AB123CD", "brand": "Renault", "model": "Trafic", "country": "AR"},
    )
    assert response.status_code == 201
    assert response.json()["type"] == "van"


def test_create_vehicle_requires_a_known_type(client, test_user):
    token = _login(client, test_user)
    for payload in (
        {"plate": "AB123CD", "brand": "Toyota", "model": "Corolla", "country": "AR"},
        {"type": "truck", "plate": "AB123CD", "brand": "Toyota", "model": "Corolla", "country": "AR"},
    ):
        assert _create(client, test_user, token, payload).status_code == 400


def test_a_bicycle_needs_no_plate_brand_or_model(client, test_user):
    token = _login(client, test_user)
    response = _create(client, test_user, token, {"type": "bicycle", "country": "AR"})
    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "bicycle"
    assert body["plate"] is None
    assert body["brand"] is None


def test_a_bicycle_keeps_an_optional_description_and_drops_a_plate(client, test_user):
    token = _login(client, test_user)
    response = _create(
        client, test_user, token,
        {"type": "bicycle", "plate": "AB123CD", "brand": "venzo", "model": "rodado 29", "country": "AR"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["plate"] is None
    assert body["brand"] == "Venzo"
    assert body["model"] == "Rodado 29"


def test_every_other_type_needs_plate_brand_and_model(client, test_user):
    token = _login(client, test_user)
    for missing in ("plate", "brand", "model"):
        payload = {"type": "motorcycle", "plate": "A123BCD", "brand": "Honda", "model": "XR 250", "country": "AR"}
        del payload[missing]
        assert _create(client, test_user, token, payload).status_code == 400


def test_fill_in_the_type_of_a_vehicle_saved_before_types(client, test_user, db):
    from app.models import Vehicle

    legacy = Vehicle(user_id=test_user.id, plate="AC745QF", brand="Chevrolet", model="Cruze", country="AR")
    db.add(legacy)
    db.commit()
    token = _login(client, test_user)
    headers = {"Authorization": f"Bearer {token}"}

    listed = client.get(f"/users/{test_user.id}/vehicles", headers=headers).json()
    assert listed[0]["type"] is None

    response = client.patch(f"/users/{test_user.id}/vehicles/{legacy.id}", json={"type": "car"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["type"] == "car"

    # A vehicle with a plate is never a bicycle.
    bad = client.patch(f"/users/{test_user.id}/vehicles/{legacy.id}", json={"type": "bicycle"}, headers=headers)
    assert bad.status_code == 400


def test_fill_in_the_type_of_someone_elses_vehicle_is_forbidden(client, test_user, db):
    from app.models import Vehicle

    other = _other_user(db)
    vehicle = Vehicle(user_id=other.id, plate="AC745QF", brand="Chevrolet", model="Cruze", country="AR")
    db.add(vehicle)
    db.commit()
    token = _login(client, test_user)

    response = client.patch(
        f"/users/{other.id}/vehicles/{vehicle.id}", json={"type": "car"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403
