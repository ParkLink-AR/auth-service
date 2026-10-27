import uuid

from app.config import Settings
from app.demo_seed import DRIVER_COUNT, OWNERS, driver_id, owner_id, seed_demo_users
from app.models import AccountType, User, UserStatus
from app.security import verify_password


def test_creates_the_demo_owners_and_drivers(db):
    created = seed_demo_users(db)

    assert created == len(OWNERS) + DRIVER_COUNT
    owners = db.query(User).filter(User.account_type == AccountType.OWNER).all()
    drivers = db.query(User).filter(User.account_type == AccountType.DRIVER).all()
    assert len(owners) == len(OWNERS)
    assert len(drivers) == DRIVER_COUNT


def test_ids_are_the_fixed_ones_other_services_rely_on(db):
    seed_demo_users(db)

    assert db.get(User, owner_id(1)).first_name == "Marcelo"
    assert str(owner_id(1)) == "0e000000-0000-4000-8000-000000000001"
    assert str(driver_id(60)) == "de000000-0000-4000-8000-000000000060"
    assert db.get(User, driver_id(60)) is not None
    assert db.get(User, driver_id(61)) is None


def test_is_idempotent(db):
    seed_demo_users(db)

    assert seed_demo_users(db) == 0
    assert db.query(User).count() == len(OWNERS) + DRIVER_COUNT


def test_only_creates_what_is_missing(db):
    seed_demo_users(db)
    db.delete(db.get(User, driver_id(5)))
    db.commit()

    assert seed_demo_users(db) == 1
    assert db.get(User, driver_id(5)) is not None


def test_nobody_can_log_in_with_them(db):
    seed_demo_users(db)
    user = db.get(User, owner_id(1))

    for guess in ("Password123", "demo", "", user.email):
        assert not verify_password(guess, user.password_hash)


def test_they_look_like_normal_active_verified_accounts(db):
    seed_demo_users(db)

    for user in db.query(User).all():
        assert user.status == UserStatus.ACTIVE
        assert user.email_verified and user.phone_verified
        assert user.first_name and user.last_name
        assert user.email.endswith("@demo.parklink.com.ar")


def test_every_driver_has_a_different_full_name(db):
    seed_demo_users(db)

    names = [(u.first_name, u.last_name) for u in db.query(User).filter(User.account_type == AccountType.DRIVER)]
    assert len(set(names)) == DRIVER_COUNT


def test_emails_are_unique_and_plain_ascii(db):
    seed_demo_users(db)

    emails = [u.email for u in db.query(User).all()]
    assert len(set(emails)) == len(emails)
    assert all(email.isascii() for email in emails)


def test_does_not_touch_real_accounts(db, test_user):
    seed_demo_users(db)

    assert db.get(User, test_user.id).email == test_user.email
    assert isinstance(test_user.id, uuid.UUID) or test_user.id


def test_is_off_unless_asked_for():
    assert Settings.model_fields["SEED_DEMO_DATA"].default is False
