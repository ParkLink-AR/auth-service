import os
from datetime import date
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["JWT_SECRET"] = "test-secret"
os.environ.setdefault("SKIP_EMAIL_VERIFICATION", "false")

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import User, UserStatus
from app.security import hash_password
from main import app

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _stamp_alembic_head() -> None:
    """The app's own startup lifespan runs `alembic upgrade head` against this
    same sqlite file (see app/alembic_utils.py). Since this fixture builds the
    schema directly from the current models (always up to date), stamping the
    version table as already-head keeps that startup migration a no-op here --
    otherwise it would try to re-apply column-adding migrations against a
    schema that already has them.
    """
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", SQLALCHEMY_DATABASE_URL)
    command.stamp(config, "head")


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    _stamp_alembic_head()
    db_session = TestingSessionLocal()
    yield db_session
    db_session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db):
    user = User(
        email="test@example.com",
        phone="+541100000000",
        first_name="Test",
        last_name="User",
        dni="30111222",
        birth_date=date(1990, 1, 1),
        password_hash=hash_password("Password123"),
        email_verified=True,
        phone_verified=True,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def valid_user_data():
    return {
        "email": "newuser@example.com",
        "phone": "+5491100000099",
        "first_name": "New",
        "last_name": "User",
        "dni": "30999888",
        "birth_date": "1990-01-01",
        "password": "SecurePass123",
        "device_id": "device-abc",
        "device_name": "iPhone 15",
    }
