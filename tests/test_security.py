from uuid import uuid4

from app import security


def test_hash_password_and_verify():
    hashed = security.hash_password("Password123")
    assert hashed != "Password123"
    assert security.verify_password("Password123", hashed)
    assert not security.verify_password("wrong-password", hashed)


def test_access_token_roundtrip():
    user_id = uuid4()
    token = security.create_access_token(user_id)
    payload = security.decode_access_token(token)

    assert payload is not None
    assert payload["sub"] == str(user_id)
    assert payload["type"] == "access"


def test_decode_access_token_rejects_garbage():
    assert security.decode_access_token("not-a-valid-token") is None


def test_opaque_token_is_random_and_hash_is_deterministic():
    token_a = security.generate_opaque_token()
    token_b = security.generate_opaque_token()
    assert token_a != token_b

    assert security.hash_token(token_a) == security.hash_token(token_a)
    assert security.hash_token(token_a) != security.hash_token(token_b)
