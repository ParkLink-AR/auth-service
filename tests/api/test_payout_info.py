import uuid
from datetime import date

from app.models import User
from app.security import hash_password

VALID_CBU = "2850590940090418135201"
VALID_CUIL = "20123456789"


def _login(client, test_user):
    response = client.post(
        "/auth/login",
        json={"email": test_user.email, "password": "Password123", "device_id": "d1"},
    )
    return response.json()["access_token"]


def _other_user(db, **overrides):
    defaults = dict(
        email="payout-other@example.com",
        phone="+5491100005566",
        first_name="Other",
        last_name="User",
        dni="30555666",
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


# -------------------------
# Self-service payout info
# -------------------------


def test_get_payout_info_defaults_to_empty(client, test_user):
    token = _login(client, test_user)
    response = client.get(
        f"/users/{test_user.id}/payout-info", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {"cbu": None, "payout_titular": None, "cuil": None, "has_payout_info": False}


def test_get_payout_info_requires_auth(client, test_user):
    response = client.get(f"/users/{test_user.id}/payout-info")
    assert response.status_code == 401


def test_get_another_users_payout_info_is_forbidden(client, test_user):
    token = _login(client, test_user)
    response = client.get(
        f"/users/{uuid.uuid4()}/payout-info", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403


def test_update_payout_info_sets_fields_and_flips_has_payout_info(client, test_user):
    token = _login(client, test_user)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.put(
        f"/users/{test_user.id}/payout-info",
        json={"cbu": VALID_CBU, "payout_titular": "Test User", "cuil": VALID_CUIL},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cbu"] == VALID_CBU
    assert body["payout_titular"] == "Test User"
    assert body["cuil"] == VALID_CUIL
    assert body["has_payout_info"] is True

    get_response = client.get(f"/users/{test_user.id}/payout-info", headers=headers)
    assert get_response.json() == body


def test_update_payout_info_strips_dashes_and_spaces_from_cuil(client, test_user):
    token = _login(client, test_user)
    response = client.put(
        f"/users/{test_user.id}/payout-info",
        json={"cbu": VALID_CBU, "payout_titular": "Test User", "cuil": "20-12345678-9"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["cuil"] == "20123456789"


def test_update_payout_info_requires_self(client, test_user, db):
    other = _other_user(db)
    token = _login(client, test_user)
    response = client.put(
        f"/users/{other.id}/payout-info",
        json={"cbu": VALID_CBU, "payout_titular": "Test User", "cuil": VALID_CUIL},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_update_payout_info_rejects_wrong_length_cbu(client, test_user):
    token = _login(client, test_user)
    response = client.put(
        f"/users/{test_user.id}/payout-info",
        json={"cbu": "123", "payout_titular": "Test User", "cuil": VALID_CUIL},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


def test_update_payout_info_rejects_non_numeric_cbu(client, test_user):
    token = _login(client, test_user)
    response = client.put(
        f"/users/{test_user.id}/payout-info",
        json={"cbu": "abcdefghij1234567890ab", "payout_titular": "Test User", "cuil": VALID_CUIL},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


def test_update_payout_info_rejects_wrong_length_cuil(client, test_user):
    token = _login(client, test_user)
    response = client.put(
        f"/users/{test_user.id}/payout-info",
        json={"cbu": VALID_CBU, "payout_titular": "Test User", "cuil": "123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


def test_update_payout_info_rejects_non_numeric_cuil(client, test_user):
    token = _login(client, test_user)
    response = client.put(
        f"/users/{test_user.id}/payout-info",
        json={"cbu": VALID_CBU, "payout_titular": "Test User", "cuil": "2X-1234567-9"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


def test_update_payout_info_rejects_empty_titular(client, test_user):
    token = _login(client, test_user)
    response = client.put(
        f"/users/{test_user.id}/payout-info",
        json={"cbu": VALID_CBU, "payout_titular": "   ", "cuil": VALID_CUIL},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


# -------------------------
# Internal endpoint (parking-service -> auth-service, no auth)
# -------------------------


def test_internal_payout_status_true_when_all_fields_set(client, test_user, db):
    test_user.cbu = VALID_CBU
    test_user.payout_titular = "Test User"
    test_user.cuil = VALID_CUIL
    db.add(test_user)
    db.commit()

    response = client.get(f"/internal/users/{test_user.id}/payout-status")
    assert response.status_code == 200
    assert response.json() == {"has_payout_info": True}


def test_internal_payout_status_false_when_incomplete(client, test_user):
    response = client.get(f"/internal/users/{test_user.id}/payout-status")
    assert response.status_code == 200
    assert response.json() == {"has_payout_info": False}


def test_internal_payout_status_requires_no_auth_header(client, test_user):
    # No Authorization header sent at all -- this must not 401.
    response = client.get(f"/internal/users/{test_user.id}/payout-status")
    assert response.status_code == 200


def test_internal_payout_status_404_for_unknown_user(client):
    response = client.get(f"/internal/users/{uuid.uuid4()}/payout-status")
    assert response.status_code == 404


def test_update_payout_info_rejects_cbu_with_wrong_check_digit(client, test_user):
    token = _login(client, test_user)
    response = client.put(
        f"/users/{test_user.id}/payout-info",
        json={"cbu": "2850590940090418135202", "payout_titular": "Test User", "cuil": VALID_CUIL},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code in (400, 422)
