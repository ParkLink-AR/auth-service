import uuid
from datetime import date

from app.models import User
from app.security import hash_password

# These endpoints deliberately have no in-handler auth check -- the gateway
# gates /admin/* on the `role: admin` JWT claim before the request ever
# reaches this service (see app/api/admin.py). So these tests hit them
# directly, with no token, the way the service itself would receive them.


def _make_user(db, **overrides):
    defaults = dict(
        email="alice.owner@example.com",
        phone="+5491100009900",
        first_name="Alice",
        last_name="Ownerson",
        dni="30999000",
        birth_date=date(1990, 1, 1),
        password_hash=hash_password("Password123"),
        email_verified=True,
        phone_verified=True,
    )
    defaults.update(overrides)
    user = User(**defaults)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_admin_search_matches_partial_email(client, db):
    _make_user(db)
    response = client.get("/admin/users", params={"query": "alice.owner"})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    row = body[0]
    assert row["email"] == "alice.owner@example.com"
    assert set(row.keys()) == {
        "id",
        "email",
        "phone",
        "first_name",
        "last_name",
        "account_type",
        "status",
        "created_at",
    }


def test_admin_search_is_case_insensitive(client, db):
    _make_user(db)
    response = client.get("/admin/users", params={"query": "ALICE"})
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_admin_search_matches_first_and_last_name(client, db):
    _make_user(db)
    assert client.get("/admin/users", params={"query": "Owners"}).json()
    assert client.get("/admin/users", params={"query": "lice"}).json()


def test_admin_search_matches_phone_and_dni(client, db):
    _make_user(db)
    assert client.get("/admin/users", params={"query": "1100009900"}).json()
    assert client.get("/admin/users", params={"query": "30999000"}).json()


def test_admin_search_no_match_returns_empty_list(client, db):
    _make_user(db)
    response = client.get("/admin/users", params={"query": "nobody-like-this"})
    assert response.status_code == 200
    assert response.json() == []


def test_admin_search_caps_results_at_50(client, db):
    for i in range(55):
        _make_user(
            db,
            email=f"bulk{i}@example.com",
            phone=f"+549110000{i:04d}",
            dni=f"40{i:06d}",
        )
    response = client.get("/admin/users", params={"query": "bulk"})
    assert response.status_code == 200
    assert len(response.json()) == 50


def test_admin_user_detail_includes_payout_and_extra_fields(client, db):
    user = _make_user(
        db,
        cbu="1234567890123456789012",
        payout_titular="Alice Ownerson",
        cuil="20123456789",
    )
    response = client.get(f"/admin/users/{user.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(user.id)
    assert body["cbu"] == "1234567890123456789012"
    assert body["payout_titular"] == "Alice Ownerson"
    assert body["cuil"] == "20123456789"
    assert body["has_payout_info"] is True
    assert body["email_verified"] is True
    assert body["phone_verified"] is True
    assert "last_login_at" in body


def test_admin_user_detail_has_payout_info_false_when_incomplete(client, db):
    user = _make_user(db, cbu="1234567890123456789012")
    response = client.get(f"/admin/users/{user.id}")
    assert response.status_code == 200
    assert response.json()["has_payout_info"] is False


def test_admin_user_detail_404_for_unknown_user(client, db):
    response = client.get(f"/admin/users/{uuid.uuid4()}")
    assert response.status_code == 404
