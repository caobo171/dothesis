from unittest.mock import patch

import pytest

from app.google_auth import verify_google_id_token


def test_returns_normalized_user_info(monkeypatch):
    monkeypatch.setenv("OPENDRAFT_GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    from app import settings as settings_mod
    settings_mod._settings = None

    fake_payload = {
        "sub": "11223344",
        "email": "Alice@Gmail.COM",
        "name": "Alice Test",
        "email_verified": True,
        "aud": "test-client-id.apps.googleusercontent.com",
    }
    with patch("app.google_auth.gid.verify_oauth2_token", return_value=fake_payload):
        info = verify_google_id_token("FAKE_TOKEN")
    assert info["google_id"] == "11223344"
    assert info["email"] == "alice@gmail.com"
    assert info["name"] == "Alice Test"


def test_raises_on_bad_token(monkeypatch):
    monkeypatch.setenv("OPENDRAFT_GOOGLE_CLIENT_ID", "x")
    from app import settings as settings_mod
    settings_mod._settings = None
    with patch("app.google_auth.gid.verify_oauth2_token", side_effect=ValueError("bad")):
        with pytest.raises(ValueError):
            verify_google_id_token("BAD")
