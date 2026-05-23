"""Unit tests for the extended UserOut/_to_out shape.

Pure-Python: avoids the INET-related TestClient bug in the auth flow.
"""
import uuid

from app.models import User
from app.routers.auth import UserOut, _to_out


def _make_user(email: str, *, username: str | None = None, credit: int = 0) -> User:
    return User(
        id=uuid.uuid4(),
        email=email,
        username=username,
        password_hash="x",
        credit=credit,
    )


def test_user_out_contains_new_fields():
    fields = set(UserOut.model_fields.keys())
    assert {"id", "email", "username", "credit", "is_super_admin"} <= fields


def test_to_out_marks_seeded_admin():
    user = _make_user("cao.nv17@gmail.com", username="cao", credit=42)
    out = _to_out(user)
    assert out.email == "cao.nv17@gmail.com"
    assert out.username == "cao"
    assert out.credit == 42
    assert out.is_super_admin is True


def test_to_out_marks_regular_user_as_non_admin():
    user = _make_user("alice@example.com", credit=0)
    out = _to_out(user)
    assert out.is_super_admin is False
    assert out.credit == 0
    assert out.username is None


def test_to_out_is_case_insensitive_for_admin():
    user = _make_user("CAO.NV17@GMAIL.COM")
    assert _to_out(user).is_super_admin is True
