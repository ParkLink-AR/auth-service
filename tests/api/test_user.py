import uuid
from datetime import date

import pytest

from app.models import User, VerificationToken, VerificationTokenType
from app.security import hash_password, hash_token

FAKE_R2_PUBLIC_URL = "https://fake-bucket.test"


@pytest.fixture(autouse=True)
def _fake_storage(monkeypatch):
    """Avatars go through app.utils.storage (R2/S3) now instead of local
    disk -- tests fake that boundary with an in-memory dict instead of
    hitting the network, keyed the same way storage.upload_bytes's returned
    URL would decode (see app/utils/storage.py)."""
    from app.utils import storage

    store: dict[str, bytes] = {}

    def fake_upload_bytes(key: str, data: bytes, content_type: str) -> str:
        store[key] = data
        return f"{FAKE_R2_PUBLIC_URL}/{key}"

    def fake_delete_object(url: str | None) -> None:
        if not url or not url.startswith(f"{FAKE_R2_PUBLIC_URL}/"):
            return
        store.pop(url[len(FAKE_R2_PUBLIC_URL) + 1 :], None)

    monkeypatch.setattr(storage, "upload_bytes", fake_upload_bytes)
    monkeypatch.setattr(storage, "delete_object", fake_delete_object)
    yield store


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


# -------------------------
# Avatar upload
# -------------------------


def _fake_image_bytes(fmt: str = "PNG", size=(64, 64)) -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", size, color=(200, 30, 40)).save(buf, format=fmt)
    return buf.getvalue()


def test_upload_avatar(client, test_user):
    token = _login(client, test_user)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        f"/users/{test_user.id}/avatar",
        headers=headers,
        files={"file": ("avatar.png", _fake_image_bytes(), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["avatar_url"].startswith(f"{FAKE_R2_PUBLIC_URL}/avatars/")

    profile = client.get(f"/users/{test_user.id}", headers=headers).json()
    assert profile["avatar_url"] == body["avatar_url"]


def test_upload_avatar_replaces_previous_file(client, test_user, _fake_storage):
    token = _login(client, test_user)
    headers = {"Authorization": f"Bearer {token}"}

    first = client.post(
        f"/users/{test_user.id}/avatar",
        headers=headers,
        files={"file": ("avatar.png", _fake_image_bytes(), "image/png")},
    )
    first_key = first.json()["avatar_url"].removeprefix(f"{FAKE_R2_PUBLIC_URL}/")
    assert first_key in _fake_storage

    second = client.post(
        f"/users/{test_user.id}/avatar",
        headers=headers,
        files={"file": ("avatar2.png", _fake_image_bytes(size=(80, 80)), "image/png")},
    )
    second_key = second.json()["avatar_url"].removeprefix(f"{FAKE_R2_PUBLIC_URL}/")

    assert second_key != first_key
    assert first_key not in _fake_storage
    assert second_key in _fake_storage


def test_upload_avatar_rejects_wrong_content_type(client, test_user):
    token = _login(client, test_user)
    response = client.post(
        f"/users/{test_user.id}/avatar",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("avatar.gif", _fake_image_bytes(fmt="GIF"), "image/gif")},
    )
    assert response.status_code == 400


def test_upload_avatar_rejects_file_disguised_as_image(client, test_user):
    token = _login(client, test_user)
    response = client.post(
        f"/users/{test_user.id}/avatar",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("avatar.png", b"not actually a png", "image/png")},
    )
    assert response.status_code == 400


def _fake_noise_image_bytes(size=(2000, 2000)) -> bytes:
    # Random pixel data barely compresses under PNG's DEFLATE, unlike a flat
    # fill (which would collapse to a few KB regardless of dimensions) -- this
    # is what actually produces bytes over the size limit.
    import os
    from io import BytesIO

    from PIL import Image

    width, height = size
    data = os.urandom(width * height * 3)
    buf = BytesIO()
    Image.frombytes("RGB", size, data).save(buf, format="PNG")
    return buf.getvalue()


def test_upload_avatar_rejects_oversized_file(client, test_user):
    from app.utils import avatar as avatar_module

    token = _login(client, test_user)
    oversized = _fake_noise_image_bytes()
    assert len(oversized) > avatar_module.MAX_AVATAR_SIZE_BYTES

    response = client.post(
        f"/users/{test_user.id}/avatar",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("avatar.png", oversized, "image/png")},
    )
    assert response.status_code == 400


def test_upload_avatar_requires_self(client, test_user, db):
    other = User(
        email="otheravatar@example.com",
        phone="+5491100002233",
        first_name="Other",
        last_name="User",
        dni="30222333",
        birth_date=date(1990, 1, 1),
        password_hash=hash_password("Password123"),
        email_verified=True,
        phone_verified=True,
    )
    db.add(other)
    db.commit()
    db.refresh(other)

    token = _login(client, test_user)
    response = client.post(
        f"/users/{other.id}/avatar",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("avatar.png", _fake_image_bytes(), "image/png")},
    )
    assert response.status_code == 403


def test_verify_current_password_accepts_correct_password(client, test_user):
    token = _login(client, test_user)
    response = client.post(
        f"/users/{test_user.id}/password/verify",
        json={"current_password": "Password123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


def test_verify_current_password_rejects_wrong_password(client, test_user):
    token = _login(client, test_user)
    response = client.post(
        f"/users/{test_user.id}/password/verify",
        json={"current_password": "WrongPassword1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_verify_current_password_requires_self(client, test_user, db):
    other = User(
        email="otherpwverify@example.com",
        phone="+5491100002244",
        first_name="Other",
        last_name="User",
        dni="30222334",
        birth_date=date(1990, 1, 1),
        password_hash=hash_password("Password123"),
        email_verified=True,
        phone_verified=True,
    )
    db.add(other)
    db.commit()
    db.refresh(other)

    token = _login(client, test_user)
    response = client.post(
        f"/users/{other.id}/password/verify",
        json={"current_password": "Password123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_change_password_requires_correct_current_password(client, test_user):
    token = _login(client, test_user)
    response = client.put(
        f"/users/{test_user.id}/password",
        json={"current_password": "WrongPassword1", "new_password": "NewPassword456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_change_password_rejects_weak_new_password(client, test_user):
    token = _login(client, test_user)
    response = client.put(
        f"/users/{test_user.id}/password",
        json={"current_password": "Password123", "new_password": "weak"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


def test_change_password_updates_and_allows_login_with_new_password(client, test_user, db):
    token = _login(client, test_user)
    response = client.put(
        f"/users/{test_user.id}/password",
        json={"current_password": "Password123", "new_password": "NewPassword456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200

    old_login = client.post(
        "/auth/login", json={"email": test_user.email, "password": "Password123"}
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/auth/login", json={"email": test_user.email, "password": "NewPassword456"}
    )
    assert new_login.status_code == 200


def test_change_password_requires_self(client, test_user, db):
    other = User(
        email="otherpwchange@example.com",
        phone="+5491100002255",
        first_name="Other",
        last_name="User",
        dni="30222335",
        birth_date=date(1990, 1, 1),
        password_hash=hash_password("Password123"),
        email_verified=True,
        phone_verified=True,
    )
    db.add(other)
    db.commit()
    db.refresh(other)

    token = _login(client, test_user)
    response = client.put(
        f"/users/{other.id}/password",
        json={"current_password": "Password123", "new_password": "NewPassword456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_phone_change_code_that_failed_to_send_is_undone(client, test_user, db, monkeypatch):
    from app.exceptions.handler import ServiceException

    def failing_send(**_kwargs):
        raise ServiceException(status_code=502, title="Bad Gateway", detail="Error sending SMS.")

    token = _login(client, test_user)
    headers = {"Authorization": f"Bearer {token}"}
    monkeypatch.setattr("app.services.users.send_registration_sms", failing_send)

    failed = client.post(f"/users/{test_user.id}/phone", json={"new_phone": "+5491199997777"}, headers=headers)

    assert failed.status_code == 502
    db.refresh(test_user)
    assert test_user.pending_phone is None
    assert (
        db.query(VerificationToken)
        .filter(VerificationToken.user_id == test_user.id, VerificationToken.type == VerificationTokenType.PHONE_CHANGE)
        .count()
        == 0
    )

    # Asking again right away works.
    monkeypatch.setattr("app.services.users.send_registration_sms", lambda **_kwargs: None)
    retried = client.post(f"/users/{test_user.id}/phone", json={"new_phone": "+5491199997777"}, headers=headers)
    assert retried.status_code == 200
