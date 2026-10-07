from datetime import datetime, timedelta, timezone

import pytest

from app.models import User, UserStatus, Vehicle

SPOT_IDS = ["11111111-1111-1111-1111-111111111111"]
ADMIN_ID = "99999999-9999-9999-9999-999999999999"


@pytest.fixture(autouse=True)
def services(monkeypatch):
    """Fakes parking-, booking- and notifications-service (there are none to talk to in
    these tests) and records every call, so tests can assert on what the lifecycle asked
    them to do. `summary` is what booking-service reports for the account."""
    from app.utils import booking_client, notifications_client, parking_client

    state = {
        "calls": [],
        "summary": {
            "in_progress_count": 0,
            "driver_bookings_to_cancel": 1,
            "owner_bookings_to_cancel": 2,
            "owner_requests_to_reject": 1,
            "pending_payout_count": 0,
            "pending_payout_amount": 0,
        },
    }

    def record(name):
        def fake(*args, **kwargs):
            state["calls"].append((name, args))
            if name == "pause":
                return SPOT_IDS
            if name == "list_spots":
                return SPOT_IDS
            if name == "summary":
                return dict(state["summary"])
            return {}

        return fake

    monkeypatch.setattr(parking_client, "pause_owner_spots", record("pause"))
    monkeypatch.setattr(parking_client, "restore_owner_spots", record("restore"))
    monkeypatch.setattr(parking_client, "archive_owner_spots", record("archive"))
    monkeypatch.setattr(parking_client, "list_owner_spot_ids", record("list_spots"))
    monkeypatch.setattr(booking_client, "get_account_closure_summary", record("summary"))
    monkeypatch.setattr(booking_client, "cancel_account_bookings", record("cancel_bookings"))
    monkeypatch.setattr(booking_client, "anonymize_account_bookings", record("anonymize_bookings"))
    monkeypatch.setattr(notifications_client, "delete_device_tokens", record("delete_tokens"))
    return state


def _called(services, name):
    return [args for call, args in services["calls"] if call == name]


def _login(client, email="test@example.com", password="Password123"):
    return client.post("/auth/login", json={"email": email, "password": password, "device_id": "d1"})


def _auth(client):
    response = _login(client)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}, response.json()["refresh_token"]


def _request_deletion(client, user, headers, password="Password123"):
    return client.post(f"/users/{user.id}/deletion", json={"password": password}, headers=headers)


def _make_due(db, user):
    user.deletion_scheduled_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()


def _finalize(db):
    from app.services import account_lifecycle

    return account_lifecycle.finalize_due_deletions(db)


# -------------------------
# Deletion asked for by the user
# -------------------------


def test_summary_lists_what_closing_the_account_would_do(client, test_user):
    headers, _ = _auth(client)
    response = client.get(f"/users/{test_user.id}/deletion", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["blocked"] is False
    assert body["driver_bookings_to_cancel"] == 1
    assert body["owner_bookings_to_cancel"] == 2
    assert body["spot_count"] == 1


def test_summary_is_blocked_by_a_booking_in_progress(client, test_user, services):
    services["summary"]["in_progress_count"] = 1
    headers, _ = _auth(client)
    body = client.get(f"/users/{test_user.id}/deletion", headers=headers).json()
    assert body["blocked"] is True
    assert "reserva en curso" in body["blocked_reason"]


def test_deletion_requires_the_right_password(client, test_user, db, services):
    headers, _ = _auth(client)
    response = _request_deletion(client, test_user, headers, password="WrongPassword1")
    assert response.status_code == 401
    db.refresh(test_user)
    assert test_user.status == UserStatus.ACTIVE
    assert _called(services, "pause") == []


def test_deletion_is_refused_while_a_booking_is_in_progress(client, test_user, db, services):
    services["summary"]["in_progress_count"] = 1
    headers, _ = _auth(client)
    response = _request_deletion(client, test_user, headers)
    assert response.status_code == 409
    assert response.json()["code"] == "ACCOUNT_HAS_BOOKING_IN_PROGRESS"
    db.refresh(test_user)
    assert test_user.status == UserStatus.ACTIVE
    assert _called(services, "cancel_bookings") == []


def test_deletion_is_scheduled_and_closes_the_account_down(client, test_user, db, services):
    headers, refresh_token = _auth(client)
    response = _request_deletion(client, test_user, headers)
    assert response.status_code == 200
    assert response.json()["status"] == "PENDING_DELETION"

    db.refresh(test_user)
    assert test_user.status == UserStatus.PENDING_DELETION
    scheduled = test_user.deletion_scheduled_at.replace(tzinfo=timezone.utc)
    assert timedelta(days=6, hours=23) < scheduled - datetime.now(timezone.utc) <= timedelta(days=7)

    assert _called(services, "pause") == [(test_user.id,)]
    assert _called(services, "cancel_bookings") == [(test_user.id, SPOT_IDS)]
    assert _called(services, "delete_tokens") == [(test_user.id,)]
    # Every session closed -- refreshing says why.
    refreshed = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert refreshed.status_code == 403
    assert refreshed.json()["code"] == "ACCOUNT_DELETION_SCHEDULED"


def test_pending_user_gets_no_session_but_is_offered_to_reactivate(client, test_user, db):
    headers, _ = _auth(client)
    _request_deletion(client, test_user, headers)

    response = _login(client)
    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "ACCOUNT_DELETION_SCHEDULED"
    assert body["deletion_scheduled_at"]
    # The old access token doesn't work either.
    assert client.get(f"/users/{test_user.id}", headers=headers).status_code == 403


def test_reactivating_cancels_the_deletion_and_logs_in(client, test_user, db, services):
    headers, _ = _auth(client)
    _request_deletion(client, test_user, headers)

    response = client.post(
        "/auth/reactivate", json={"email": test_user.email, "password": "Password123", "device_id": "d1"}
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    profile = client.get(f"/users/{test_user.id}", headers={"Authorization": f"Bearer {token}"}).json()
    assert profile["status"] == "ACTIVE"
    assert profile["deletion_scheduled_at"] is None
    assert _called(services, "restore") == [(test_user.id,)]
    assert _login(client).status_code == 200


def test_reactivating_needs_the_right_password(client, test_user, db):
    headers, _ = _auth(client)
    _request_deletion(client, test_user, headers)
    response = client.post("/auth/reactivate", json={"email": test_user.email, "password": "WrongPassword1"})
    assert response.status_code == 401
    db.refresh(test_user)
    assert test_user.status == UserStatus.PENDING_DELETION


def test_reactivating_an_active_account_is_refused(client, test_user):
    response = client.post("/auth/reactivate", json={"email": test_user.email, "password": "Password123"})
    assert response.status_code == 409


def test_registering_with_the_data_of_an_account_being_deleted_says_so(client, test_user):
    headers, _ = _auth(client)
    _request_deletion(client, test_user, headers)
    response = client.post("/auth/registration/email/request", json={"email": test_user.email})
    assert response.status_code == 400
    assert response.json()["code"] == "ACCOUNT_PENDING_DELETION"


def test_nothing_is_wiped_before_the_grace_period_is_over(client, test_user, db):
    headers, _ = _auth(client)
    _request_deletion(client, test_user, headers)
    assert _finalize(db) == 0
    db.refresh(test_user)
    assert test_user.status == UserStatus.PENDING_DELETION
    assert test_user.email == "test@example.com"


def test_due_deletion_wipes_the_personal_data_but_keeps_the_row(client, test_user, db, services):
    db.add(Vehicle(user_id=test_user.id, plate="AB123CD", brand="Fiat", model="Uno", country="AR"))
    db.commit()
    headers, _ = _auth(client)
    _request_deletion(client, test_user, headers)
    _make_due(db, test_user)

    assert _finalize(db) == 1

    db.refresh(test_user)
    assert test_user.status == UserStatus.DELETED
    assert test_user.deleted_at is not None
    assert (test_user.first_name, test_user.last_name) == ("Usuario", "eliminado")
    assert test_user.email.startswith("eliminado-")
    assert test_user.phone is None and test_user.dni is None and test_user.birth_date is None
    assert test_user.cbu is None and test_user.avatar_url is None
    assert db.query(Vehicle).filter_by(user_id=test_user.id).count() == 0
    assert _called(services, "archive") == [(test_user.id,)]
    assert _called(services, "anonymize_bookings") == [(test_user.id,)]

    # The real email is free again and the old password doesn't open anything.
    assert db.query(User).filter_by(email="test@example.com").first() is None
    assert _login(client).status_code == 401


def test_due_deletion_waits_until_the_owner_has_been_paid(client, test_user, db, services):
    headers, _ = _auth(client)
    _request_deletion(client, test_user, headers)
    _make_due(db, test_user)
    services["summary"]["pending_payout_count"] = 2

    assert _finalize(db) == 0
    db.refresh(test_user)
    assert test_user.status == UserStatus.PENDING_DELETION

    services["summary"]["pending_payout_count"] = 0
    assert _finalize(db) == 1


def test_a_due_deletion_can_no_longer_be_cancelled_by_logging_in(client, test_user, db):
    headers, _ = _auth(client)
    _request_deletion(client, test_user, headers)
    _make_due(db, test_user)
    response = _login(client)
    assert response.status_code == 403
    assert response.json()["code"] == "ACCOUNT_DELETION_IN_PROGRESS"
    reactivate = client.post("/auth/reactivate", json={"email": test_user.email, "password": "Password123"})
    assert reactivate.json()["code"] == "ACCOUNT_DELETION_IN_PROGRESS"


# -------------------------
# Admin: suspension and reactivation
# -------------------------


def _suspend(client, user, reason="Fraude reportado"):
    return client.post(f"/admin/users/{user.id}/suspend", json={"reason": reason}, headers={"x-user-id": ADMIN_ID})


def test_admin_suspension_locks_the_account_out(client, test_user, db, services):
    headers, refresh_token = _auth(client)
    response = _suspend(client, test_user)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUSPENDED"
    assert body["suspension_reason"] == "Fraude reportado"
    assert body["suspended_by_admin_id"] == ADMIN_ID

    assert _called(services, "pause") == [(test_user.id,)]
    assert _called(services, "cancel_bookings") == [(test_user.id, SPOT_IDS)]

    # A still-valid access token stops working right away, saying why...
    profile = client.get(f"/users/{test_user.id}", headers=headers)
    assert profile.status_code == 403
    assert profile.json()["code"] == "ACCOUNT_SUSPENDED"
    # ...so does refreshing the session...
    refreshed = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert refreshed.status_code == 403
    assert refreshed.json()["code"] == "ACCOUNT_SUSPENDED"
    # ...and logging in says why, and where to write.
    login = _login(client)
    assert login.status_code == 403
    assert login.json()["code"] == "ACCOUNT_SUSPENDED"
    assert "soporte@parklink.com.ar" in login.json()["detail"]


def test_suspension_needs_a_reason(client, test_user):
    response = client.post(f"/admin/users/{test_user.id}/suspend", json={"reason": ""})
    assert response.status_code == 400


def test_only_an_admin_reactivation_lifts_a_suspension(client, test_user, db, services):
    _suspend(client, test_user)

    response = client.post(f"/admin/users/{test_user.id}/reactivate", headers={"x-user-id": ADMIN_ID})
    assert response.status_code == 200
    assert response.json()["status"] == "ACTIVE"
    assert response.json()["suspension_reason"] is None
    assert _called(services, "restore") == [(test_user.id,)]
    assert _login(client).status_code == 200


def test_reactivating_an_account_that_isnt_suspended_is_refused(client, test_user):
    response = client.post(f"/admin/users/{test_user.id}/reactivate")
    assert response.status_code == 409


def test_suspending_replaces_a_pending_deletion(client, test_user, db):
    headers, _ = _auth(client)
    _request_deletion(client, test_user, headers)
    _suspend(client, test_user)
    db.refresh(test_user)
    assert test_user.status == UserStatus.SUSPENDED
    assert test_user.deletion_scheduled_at is None


# -------------------------
# Admin: deletion at the holder's request
# -------------------------


def test_admin_deletion_wipes_the_account_right_away(client, test_user, db, services):
    _suspend(client, test_user)
    response = client.post(
        f"/admin/users/{test_user.id}/deletion",
        json={"reason": "Lo pidió por mail el 07/10"},
        headers={"x-user-id": ADMIN_ID},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "DELETED"
    assert body["deletion_reason"] == "Lo pidió por mail el 07/10"
    assert body["deletion_requested_by_admin_id"] == ADMIN_ID
    assert body["email"].startswith("eliminado-")


def test_admin_deletion_waits_for_pending_payouts(client, test_user, db, services):
    services["summary"]["pending_payout_count"] = 1
    response = client.post(
        f"/admin/users/{test_user.id}/deletion", json={"reason": "Pedido del titular"}, headers={"x-user-id": ADMIN_ID}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "PENDING_DELETION"
    # It can't be undone by logging in.
    assert _login(client).json()["code"] == "ACCOUNT_DELETION_IN_PROGRESS"


def test_admin_deletion_is_refused_while_a_booking_is_in_progress(client, test_user, services):
    services["summary"]["in_progress_count"] = 1
    response = client.post(
        f"/admin/users/{test_user.id}/deletion", json={"reason": "Pedido del titular"}, headers={"x-user-id": ADMIN_ID}
    )
    assert response.status_code == 409


def test_internal_account_status(client, test_user):
    response = client.get(f"/internal/users/{test_user.id}/account-status")
    assert response.status_code == 200
    assert response.json() == {"status": "ACTIVE"}
