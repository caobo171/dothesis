import os
from unittest.mock import MagicMock

import pytest

from app.admin_config import SUPER_ADMIN_EMAILS, is_super_admin, _load_extra_emails


def _user(email: str):
    u = MagicMock()
    u.email = email
    return u


def test_seeded_admin_is_recognised():
    assert "cao.nv17@gmail.com" in SUPER_ADMIN_EMAILS
    assert is_super_admin(_user("cao.nv17@gmail.com")) is True


def test_non_admin_email_rejected():
    assert is_super_admin(_user("alice@example.com")) is False


def test_admin_check_is_case_insensitive():
    assert is_super_admin(_user("CAO.NV17@GMAIL.COM")) is True


def test_env_var_extends_allowlist(monkeypatch):
    monkeypatch.setenv("OPENDRAFT_SUPER_ADMIN_EMAILS", "extra1@x.com, EXTRA2@y.com")
    extras = _load_extra_emails()
    assert extras == frozenset({"extra1@x.com", "extra2@y.com"})


def test_env_var_empty_returns_empty_set(monkeypatch):
    monkeypatch.delenv("OPENDRAFT_SUPER_ADMIN_EMAILS", raising=False)
    assert _load_extra_emails() == frozenset()
