from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.auth_admin import require_admin


def _user(email: str):
    u = MagicMock()
    u.email = email
    return u


def test_admin_user_passes_through():
    user = _user("cao.nv17@gmail.com")
    assert require_admin(user=user) is user


def test_non_admin_raises_403():
    user = _user("alice@example.com")
    with pytest.raises(HTTPException) as exc:
        require_admin(user=user)
    assert exc.value.status_code == 403
    assert exc.value.detail["error"]["code"] == "forbidden"
