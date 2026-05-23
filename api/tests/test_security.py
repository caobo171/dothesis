import pytest

from app.security import hash_password, sign_session_id, verify_password, verify_session_cookie


@pytest.fixture(autouse=True)
def _bind_db():
    yield


def test_password_round_trip():
    h = hash_password("secret123")
    assert verify_password("secret123", h)
    assert not verify_password("wrong", h)


def test_session_cookie_round_trip():
    cookie = sign_session_id("sess-xyz", secret="abc")
    assert verify_session_cookie(cookie, secret="abc") == "sess-xyz"


def test_session_cookie_rejects_tampered():
    cookie = sign_session_id("sess-xyz", secret="abc")
    tampered = cookie[:-2] + "xx"
    with pytest.raises(ValueError):
        verify_session_cookie(tampered, secret="abc")


def test_session_cookie_rejects_wrong_secret():
    cookie = sign_session_id("sess-xyz", secret="abc")
    with pytest.raises(ValueError):
        verify_session_cookie(cookie, secret="other")
