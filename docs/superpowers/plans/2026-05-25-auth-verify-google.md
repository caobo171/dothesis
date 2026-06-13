# Auth: email verification + password reset + Google sign-in — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Survify-style auth in dothesis: email-verified signup with SES-delivered confirmation links, password reset, "Sign in with Google", and account auto-linking.

**Architecture:** Backend adds three small modules (`mail.py`, `auth_tokens.py`, `google_auth.py`) and extends `routers/auth.py` with five new endpoints (`/verify`, `/resend-verification`, `/forgot-password`, `/reset-password`, `/google`). Login is blocked until `email_verified=True`. Tokens for email links are `itsdangerous`-signed JWT-style strings (no DB row). Frontend gets four new pages plus a `GoogleSignInButton` component built on Google Identity Services. Sessions remain cookie-based for app traffic; JWT tokens are only used inside email links.

**Tech Stack:** FastAPI / SQLAlchemy 2 / Alembic / boto3 (SESv2) / itsdangerous / google-auth 2.x; Next.js 16 / React 19 / Tailwind / Google Identity Services (vanilla `https://accounts.google.com/gsi/client`).

---

## File structure

**API (`api/app/`):**
- New: `mail.py` — SESv2 client wrapper with dummy mode.
- New: `mail_templates/verify_email.html`, `mail_templates/reset_password.html`.
- New: `auth_tokens.py` — `make_verify_token`, `make_reset_token`, `decode_token`.
- New: `google_auth.py` — `verify_google_id_token`.
- Modify: `settings.py` — five new env-backed fields.
- Modify: `models.py` — `User.username` becomes `nullable=False, unique=True`; add `email_verified`, `google_id`, `last_login`, `last_verify_sent_at`.
- Modify: `routers/auth.py` — signup/login shape changes + five new endpoints.
- Modify: `pyproject.toml` — add `google-auth>=2.34`.
- New migration: `migrations/versions/<rev>_auth_verify_google.py`.

**API tests (`api/tests/`):**
- `test_auth_tokens.py`, `test_mail_dummy.py`, `test_google_auth.py`,
  `test_auth_signup_verify.py`, `test_auth_login_gate.py`, `test_auth_resend.py`,
  `test_auth_password_reset.py`, `test_auth_google.py`.

**Web (`web/`):**
- New: `app/components/auth/GoogleSignInButton.tsx`.
- Modify: `app/login/page.jsx` (full rewrite in Tailwind).
- Modify: `app/signup/page.jsx` (full rewrite in Tailwind + username + Google).
- New: `app/wait-verify/page.jsx`.
- New: `app/verify/page.jsx`.
- New: `app/forgot-password/page.jsx`.
- New: `app/reset-password/page.jsx`.
- Modify: `proxy.js` — add four routes to `PUBLIC_PATHS`.

---

## Pre-flight

- [ ] **P1: Working tree clean**

Run: `git status --short`. Expected: empty.

- [ ] **P2: Baseline test count**

Run from `api/`: `.\.venv\Scripts\python.exe -m pytest -q --tb=no 2>&1 | findstr "passed failed"`. Note the line — that's the count to beat.

---

## Task 1: Add Settings fields

**Files:**
- Modify: `api/app/settings.py`

- [ ] **Step 1: Add the five new fields**

Insert after the existing `dothesis_payments` line:

```python
    mail_from: str = Field(alias="DOTHESIS_MAIL_FROM", default="")
    mail_region: str = Field(alias="DOTHESIS_MAIL_REGION", default="ap-southeast-1")
    dothesis_mail: str = Field(alias="DOTHESIS_MAIL", default="")
    google_client_id: str = Field(alias="DOTHESIS_GOOGLE_CLIENT_ID", default="")
    signup_bonus_credits: int = Field(alias="DOTHESIS_SIGNUP_BONUS_CREDITS", default=100)
```

- [ ] **Step 2: Verify**

Run: `cd api && .\.venv\Scripts\python.exe -c "from app.settings import get_settings; s = get_settings(); print(s.mail_from, s.mail_region, s.dothesis_mail, s.google_client_id, s.signup_bonus_credits)"`
Expected: ` ap-southeast-1   100`

- [ ] **Step 3: Commit**

```bash
git add api/app/settings.py
git commit -m "feat(api): settings for SES mail + Google OAuth + signup bonus"
```

---

## Task 2: Add google-auth dependency

**Files:**
- Modify: `api/pyproject.toml`

- [ ] **Step 1: Add to dependencies**

Open `api/pyproject.toml`. Find the `dependencies = [...]` array under `[project]`. Append:

```
  "google-auth>=2.34",
```

- [ ] **Step 2: Install into venv**

Run: `cd api && .\.venv\Scripts\python.exe -m pip install -e ".[dev]"`
Expected: `google-auth` and its transitive deps (rsa, pyasn1, etc.) install successfully.

- [ ] **Step 3: Verify import**

Run: `cd api && .\.venv\Scripts\python.exe -c "from google.oauth2 import id_token; from google.auth.transport import requests; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add api/pyproject.toml
git commit -m "build(api): add google-auth for Google id_token verification"
```

---

## Task 3: User model schema updates

**Files:**
- Modify: `api/app/models.py`

- [ ] **Step 1: Edit the `User` class**

Replace the existing `User` class definition with:

```python
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    credit: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    email_verified: Mapped[bool] = mapped_column(default=False, server_default="false", nullable=False)
    google_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verify_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 2: Verify the model imports**

Run: `cd api && .\.venv\Scripts\python.exe -c "from app.models import User; print(list(User.__table__.columns.keys()))"`
Expected: list including `username, email_verified, google_id, last_login, last_verify_sent_at`.

- [ ] **Step 3: Commit**

```bash
git add api/app/models.py
git commit -m "feat(api): User gains email_verified, google_id, last_login, unique username"
```

---

## Task 4: Alembic migration with username backfill

**Files:**
- Create: `api/migrations/versions/<rev>_auth_verify_google.py`

- [ ] **Step 1: Generate revision**

Run from `api/`:
```
.\.venv\Scripts\python.exe -m alembic revision -m "auth_verify_google"
```
Note the new revision id. Find the latest head with `.\.venv\Scripts\python.exe -m alembic heads` (should be `35f297a99bf6` from the announcements migration). Set the new file's `down_revision = "35f297a99bf6"`.

- [ ] **Step 2: Write upgrade and downgrade**

Replace the body of the new file with:

```python
"""auth_verify_google

Revision ID: <KEEP AUTO ID>
Revises: 35f297a99bf6
Create Date: ...
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "<KEEP AUTO ID>"
down_revision: Union[str, None] = "35f297a99bf6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Backfill username for any rows missing one BEFORE applying NOT NULL/UNIQUE.
    # Pick "<email-prefix><4 random digits>", retrying on collision.
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, email FROM users WHERE username IS NULL")).all()
    import random, re
    used = {r[0] for r in bind.execute(sa.text("SELECT username FROM users WHERE username IS NOT NULL"))}
    for uid, email in rows:
        prefix = re.sub(r"[^a-zA-Z0-9]", "", (email or "user").split("@")[0])[:24] or "user"
        for _ in range(50):
            candidate = f"{prefix}{random.randint(1000, 9999)}"
            if candidate not in used:
                break
        used.add(candidate)
        bind.execute(
            sa.text("UPDATE users SET username = :u WHERE id = :id"),
            {"u": candidate, "id": uid},
        )

    op.alter_column("users", "username", existing_type=sa.String(64), nullable=False)
    op.create_unique_constraint("users_username_key", "users", ["username"])

    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("users", sa.Column("google_id", sa.String(64)))
    op.create_unique_constraint("users_google_id_key", "users", ["google_id"])
    op.add_column("users", sa.Column("last_login", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("last_verify_sent_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("users", "last_verify_sent_at")
    op.drop_column("users", "last_login")
    op.drop_constraint("users_google_id_key", "users", type_="unique")
    op.drop_column("users", "google_id")
    op.drop_column("users", "email_verified")
    op.drop_constraint("users_username_key", "users", type_="unique")
    op.alter_column("users", "username", existing_type=sa.String(64), nullable=True)
```

- [ ] **Step 3: Verify head**

Run from `api/`: `.\.venv\Scripts\python.exe -m alembic heads`
Expected: your new revision id `(head)`.

- [ ] **Step 4: Commit**

```bash
git add api/migrations/versions/
git commit -m "feat(api): migration for username unique + email_verified + google_id"
```

---

## Task 5: `auth_tokens.py`

**Files:**
- Create: `api/app/auth_tokens.py`
- Test: `api/tests/test_auth_tokens.py`

- [ ] **Step 1: Write failing tests**

```python
# api/tests/test_auth_tokens.py
import time
import uuid
import pytest

from app.auth_tokens import (
    VERIFY_TTL, RESET_TTL,
    make_verify_token, make_reset_token, decode_token,
)


def test_verify_token_round_trip():
    uid = uuid.uuid4()
    tok = make_verify_token(uid)
    assert isinstance(tok, str) and len(tok) > 20
    out = decode_token(tok, kind="verify", max_age=VERIFY_TTL)
    assert out == uid


def test_reset_token_round_trip():
    uid = uuid.uuid4()
    tok = make_reset_token(uid)
    assert decode_token(tok, kind="reset", max_age=RESET_TTL) == uid


def test_kind_mismatch_rejected():
    tok = make_verify_token(uuid.uuid4())
    with pytest.raises(ValueError):
        decode_token(tok, kind="reset", max_age=RESET_TTL)


def test_tampered_token_rejected():
    tok = make_verify_token(uuid.uuid4()) + "x"
    with pytest.raises(ValueError):
        decode_token(tok, kind="verify", max_age=VERIFY_TTL)


def test_expired_token_rejected():
    # Force expiry by setting max_age=0 then sleeping a moment.
    tok = make_verify_token(uuid.uuid4())
    time.sleep(1.1)
    with pytest.raises(ValueError):
        decode_token(tok, kind="verify", max_age=1)
```

- [ ] **Step 2: Run, expect ModuleNotFoundError**

```
.\.venv\Scripts\python.exe -m pytest tests/test_auth_tokens.py -v
```

- [ ] **Step 3: Implement**

```python
# api/app/auth_tokens.py
"""itsdangerous-signed JWT-style tokens for email-bound links."""
from __future__ import annotations

import uuid

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from .settings import get_settings

VERIFY_TTL = 24 * 3600   # 24 hours
RESET_TTL = 60 * 60      # 60 minutes


def _serializer() -> URLSafeTimedSerializer:
    s = get_settings()
    return URLSafeTimedSerializer(secret_key=s.session_secret, salt="auth-token")


def make_verify_token(user_id: uuid.UUID) -> str:
    return _serializer().dumps({"uid": str(user_id), "kind": "verify"})


def make_reset_token(user_id: uuid.UUID) -> str:
    return _serializer().dumps({"uid": str(user_id), "kind": "reset"})


def decode_token(token: str, *, kind: str, max_age: int) -> uuid.UUID:
    """Return the user_id, or raise ValueError on any failure."""
    try:
        data = _serializer().loads(token, max_age=max_age)
    except SignatureExpired:
        raise ValueError("token_expired")
    except BadSignature:
        raise ValueError("token_invalid")
    if not isinstance(data, dict) or data.get("kind") != kind:
        raise ValueError("token_mismatch")
    try:
        return uuid.UUID(data["uid"])
    except (KeyError, ValueError):
        raise ValueError("token_invalid")
```

- [ ] **Step 4: Run tests**

```
.\.venv\Scripts\python.exe -m pytest tests/test_auth_tokens.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add api/app/auth_tokens.py api/tests/test_auth_tokens.py
git commit -m "feat(api): signed verify/reset tokens via itsdangerous"
```

---

## Task 6: `mail.py` with dummy mode

**Files:**
- Create: `api/app/mail.py`
- Create: `api/app/mail_templates/__init__.py` (empty placeholder)
- Test: `api/tests/test_mail_dummy.py`

- [ ] **Step 1: Write failing test**

```python
# api/tests/test_mail_dummy.py
import logging
from unittest.mock import patch

from app.mail import send_template


def test_dummy_mode_when_mail_from_blank(monkeypatch, caplog):
    monkeypatch.setenv("DOTHESIS_MAIL_FROM", "")
    # Force re-init of settings
    from app import settings as settings_mod
    settings_mod._settings = None

    # Make sure the template exists so render doesn't fail
    from pathlib import Path
    tpl_dir = Path(settings_mod.__file__).parent / "mail_templates"
    tpl_dir.mkdir(parents=True, exist_ok=True)
    sample = tpl_dir / "_test_dummy.html"
    sample.write_text("<p>Hi {{username}}</p>", encoding="utf-8")
    try:
        with caplog.at_level(logging.WARNING):
            ok = send_template("alice@e.com", "_test_dummy",
                               {"username": "alice"}, "Test")
        assert ok is True
        assert any("alice@e.com" in r.message for r in caplog.records)
    finally:
        sample.unlink(missing_ok=True)


def test_real_mode_calls_ses(monkeypatch):
    monkeypatch.setenv("DOTHESIS_MAIL_FROM", "DoThesis <noreply@x.com>")
    monkeypatch.setenv("DOTHESIS_MAIL", "")
    from app import settings as settings_mod
    settings_mod._settings = None

    from pathlib import Path
    tpl_dir = Path(settings_mod.__file__).parent / "mail_templates"
    tpl_dir.mkdir(parents=True, exist_ok=True)
    sample = tpl_dir / "_test_real.html"
    sample.write_text("<p>Hi {{username}}</p>", encoding="utf-8")
    try:
        with patch("app.mail._ses") as ses_factory:
            client = ses_factory.return_value
            client.send_email.return_value = {"MessageId": "fake-123"}
            ok = send_template("alice@e.com", "_test_real",
                               {"username": "alice"}, "Test")
            assert ok is True
            client.send_email.assert_called_once()
            kwargs = client.send_email.call_args.kwargs
            assert kwargs["FromEmailAddress"] == "DoThesis <noreply@x.com>"
            assert kwargs["Destination"]["ToAddresses"] == ["alice@e.com"]
            assert "Hi alice" in kwargs["Content"]["Simple"]["Body"]["Html"]["Data"]
    finally:
        sample.unlink(missing_ok=True)
```

- [ ] **Step 2: Run, expect import failure**

```
.\.venv\Scripts\python.exe -m pytest tests/test_mail_dummy.py -v
```

- [ ] **Step 3: Implement**

Create directory `api/app/mail_templates/` (empty `__init__.py` is fine to avoid Python warnings).

```python
# api/app/mail.py
"""SESv2-backed transactional email with dummy mode for local dev."""
from __future__ import annotations

import logging
from pathlib import Path

import boto3

from .settings import get_settings

log = logging.getLogger(__name__)
_TEMPLATES_DIR = Path(__file__).parent / "mail_templates"
_client = None


def _ses():
    global _client
    if _client is None:
        s = get_settings()
        _client = boto3.client(
            "sesv2",
            region_name=s.mail_region or "ap-southeast-1",
            aws_access_key_id=s.aws_access_key,
            aws_secret_access_key=s.aws_secret_key,
        )
    return _client


def _render(template: str, vars: dict) -> str:
    path = _TEMPLATES_DIR / f"{template}.html"
    html = path.read_text(encoding="utf-8")
    for k, v in vars.items():
        html = html.replace("{{" + k + "}}", str(v))
    return html


def send_html(to: str, subject: str, html: str) -> bool:
    s = get_settings()
    if s.dothesis_mail == "dummy" or not s.mail_from:
        log.warning("mail dummy mode → to=%s subject=%s body=%s",
                    to, subject, html[:400])
        return True
    try:
        _ses().send_email(
            FromEmailAddress=s.mail_from,
            Destination={"ToAddresses": [to]},
            Content={"Simple": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Html": {"Data": html, "Charset": "UTF-8"}},
            }},
        )
        return True
    except Exception:
        log.exception("SES send failed for %s", to)
        return False


def send_template(to: str, template: str, vars: dict, subject: str) -> bool:
    html = _render(template, vars)
    return send_html(to, subject, html)
```

- [ ] **Step 4: Run tests**

```
.\.venv\Scripts\python.exe -m pytest tests/test_mail_dummy.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add api/app/mail.py api/app/mail_templates/__init__.py api/tests/test_mail_dummy.py
git commit -m "feat(api): SESv2 mail wrapper with dummy mode for local dev"
```

---

## Task 7: Email HTML templates

**Files:**
- Create: `api/app/mail_templates/verify_email.html`
- Create: `api/app/mail_templates/reset_password.html`

- [ ] **Step 1: Create `verify_email.html`**

```html
<!doctype html>
<html><body style="margin:0;padding:0;background:#f5f6fb;font-family:Helvetica,Arial,sans-serif;color:#0b0d1a;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f6fb;padding:32px 16px;">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;">
      <tr><td style="padding:32px 40px 0;text-align:center;">
        <div style="font-weight:800;font-size:20px;color:#0b0d1a;">Do<span style="color:#1c2eff;">Thesis</span></div>
      </td></tr>
      <tr><td style="padding:28px 40px 8px;">
        <h1 style="font-size:22px;margin:0 0 8px;color:#0b0d1a;">Confirm your email</h1>
        <p style="font-size:14px;line-height:1.6;color:#292c44;margin:0 0 18px;">
          Hi {{username}}, thanks for signing up. Click the button below to verify your email and finish creating your account.
        </p>
        <p style="text-align:center;margin:24px 0;">
          <a href="{{verify_url}}" style="display:inline-block;background:#1c2eff;color:#ffffff;text-decoration:none;font-weight:600;font-size:14px;padding:12px 24px;border-radius:12px;">
            Verify email
          </a>
        </p>
        <p style="font-size:12px;color:#5b5f7d;margin:18px 0 0;line-height:1.5;">
          Or paste this link into your browser:<br>
          <span style="word-break:break-all;color:#1c2eff;">{{verify_url}}</span>
        </p>
        <p style="font-size:12px;color:#8a8fa8;margin-top:24px;">
          This link expires in {{expires_hours}} hours. If you didn't sign up, ignore this email.
        </p>
      </td></tr>
      <tr><td style="padding:24px 40px 32px;text-align:center;font-size:11px;color:#8a8fa8;">
        © 2026 DoThesis
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>
```

- [ ] **Step 2: Create `reset_password.html`**

```html
<!doctype html>
<html><body style="margin:0;padding:0;background:#f5f6fb;font-family:Helvetica,Arial,sans-serif;color:#0b0d1a;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f6fb;padding:32px 16px;">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;">
      <tr><td style="padding:32px 40px 0;text-align:center;">
        <div style="font-weight:800;font-size:20px;color:#0b0d1a;">Do<span style="color:#1c2eff;">Thesis</span></div>
      </td></tr>
      <tr><td style="padding:28px 40px 8px;">
        <h1 style="font-size:22px;margin:0 0 8px;color:#0b0d1a;">Reset your password</h1>
        <p style="font-size:14px;line-height:1.6;color:#292c44;margin:0 0 18px;">
          Hi {{username}}, click the button below to choose a new password. If you didn't request this, you can safely ignore this email.
        </p>
        <p style="text-align:center;margin:24px 0;">
          <a href="{{reset_url}}" style="display:inline-block;background:#1c2eff;color:#ffffff;text-decoration:none;font-weight:600;font-size:14px;padding:12px 24px;border-radius:12px;">
            Choose new password
          </a>
        </p>
        <p style="font-size:12px;color:#5b5f7d;margin:18px 0 0;line-height:1.5;">
          Or paste this link into your browser:<br>
          <span style="word-break:break-all;color:#1c2eff;">{{reset_url}}</span>
        </p>
        <p style="font-size:12px;color:#8a8fa8;margin-top:24px;">
          This link expires in {{expires_minutes}} minutes.
        </p>
      </td></tr>
      <tr><td style="padding:24px 40px 32px;text-align:center;font-size:11px;color:#8a8fa8;">
        © 2026 DoThesis
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>
```

- [ ] **Step 3: Sanity-check render**

Run from `api/`:
```
.\.venv\Scripts\python.exe -c "from app.mail import _render; html = _render('verify_email', {'username': 'alice', 'verify_url': 'https://x.com/v?t=ABC', 'expires_hours': 24}); assert 'alice' in html and 'ABC' in html and '{{' not in html; print('ok')"
```
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add api/app/mail_templates/verify_email.html api/app/mail_templates/reset_password.html
git commit -m "feat(api): HTML email templates for verify + reset"
```

---

## Task 8: `google_auth.py` + tests

**Files:**
- Create: `api/app/google_auth.py`
- Test: `api/tests/test_google_auth.py`

- [ ] **Step 1: Write failing tests**

```python
# api/tests/test_google_auth.py
from unittest.mock import patch

import pytest

from app.google_auth import verify_google_id_token


def test_returns_normalized_user_info(monkeypatch):
    monkeypatch.setenv("DOTHESIS_GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
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
    monkeypatch.setenv("DOTHESIS_GOOGLE_CLIENT_ID", "x")
    from app import settings as settings_mod
    settings_mod._settings = None
    with patch("app.google_auth.gid.verify_oauth2_token", side_effect=ValueError("bad")):
        with pytest.raises(ValueError):
            verify_google_id_token("BAD")
```

- [ ] **Step 2: Run, expect fail**

```
.\.venv\Scripts\python.exe -m pytest tests/test_google_auth.py -v
```

- [ ] **Step 3: Implement**

```python
# api/app/google_auth.py
"""Verify Google ID tokens via the google-auth library."""
from __future__ import annotations

from google.auth.transport import requests as g_requests
from google.oauth2 import id_token as gid

from .settings import get_settings


def verify_google_id_token(id_token_str: str) -> dict:
    """Returns {email, google_id, name}. Raises ValueError if invalid."""
    s = get_settings()
    if not s.google_client_id:
        raise ValueError("google_not_configured")
    try:
        info = gid.verify_oauth2_token(id_token_str, g_requests.Request(), s.google_client_id)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(str(e))
    email = info.get("email")
    sub = info.get("sub")
    if not email or not sub:
        raise ValueError("missing_fields")
    return {
        "email": email.lower(),
        "google_id": str(sub),
        "name": info.get("name") or email.split("@")[0],
    }
```

- [ ] **Step 4: Run tests**

```
.\.venv\Scripts\python.exe -m pytest tests/test_google_auth.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add api/app/google_auth.py api/tests/test_google_auth.py
git commit -m "feat(api): Google id_token verifier"
```

---

## Task 9: Rework `/signup`

**Files:**
- Modify: `api/app/routers/auth.py`
- Test: `api/tests/test_auth_signup_verify.py`

- [ ] **Step 1: Write failing tests**

```python
# api/tests/test_auth_signup_verify.py
import re
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import User


def _client():
    return TestClient(create_app())


def test_signup_creates_user_without_session_and_sends_email():
    sent = {}
    def fake_send(to, template, vars, subject):
        sent["to"] = to
        sent["template"] = template
        sent["vars"] = vars
        return True

    with patch("app.routers.auth.send_template", side_effect=fake_send):
        c = _client()
        r = c.post("/api/v1/auth/signup",
                   json={"username": "alice123", "email": "alice@e.com",
                         "password": "supersecret"})
        assert r.status_code == 201, r.text
        assert r.json() == {"ok": True, "email": "alice@e.com"}
        # No session cookie
        assert "dothesis_session" not in c.cookies

    assert sent["to"] == "alice@e.com"
    assert sent["template"] == "verify_email"
    assert "verify_url" in sent["vars"] and sent["vars"]["verify_url"].startswith("http")

    Session = get_session_factory()
    with Session() as s:
        u = s.scalar(__import__("sqlalchemy").select(User).where(User.email == "alice@e.com"))
        assert u is not None
        assert u.email_verified is False
        assert u.username == "alice123"
        assert u.credit == 0


def test_signup_rejects_duplicate_email():
    with patch("app.routers.auth.send_template", return_value=True):
        c = _client()
        c.post("/api/v1/auth/signup",
               json={"username": "alice123", "email": "alice@e.com", "password": "supersecret"})
        r = c.post("/api/v1/auth/signup",
                   json={"username": "alice456", "email": "alice@e.com", "password": "supersecret"})
    assert r.status_code == 409
    assert r.json()["detail"]["error"]["code"] == "email_taken"


def test_signup_rejects_duplicate_username():
    with patch("app.routers.auth.send_template", return_value=True):
        c = _client()
        c.post("/api/v1/auth/signup",
               json={"username": "alice", "email": "a@e.com", "password": "supersecret"})
        r = c.post("/api/v1/auth/signup",
                   json={"username": "alice", "email": "b@e.com", "password": "supersecret"})
    assert r.status_code == 409
    assert r.json()["detail"]["error"]["code"] == "username_taken"


def test_signup_rejects_bad_username():
    c = _client()
    with patch("app.routers.auth.send_template", return_value=True):
        r = c.post("/api/v1/auth/signup",
                   json={"username": "a b", "email": "x@e.com", "password": "supersecret"})
    assert r.status_code == 422
```

- [ ] **Step 2: Run, expect failure**

```
.\.venv\Scripts\python.exe -m pytest tests/test_auth_signup_verify.py -v
```

- [ ] **Step 3: Rewrite signup endpoint**

Open `api/app/routers/auth.py`. Update the imports at the top:

```python
from datetime import datetime, timedelta, timezone
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth_tokens import VERIFY_TTL, RESET_TTL, make_verify_token, make_reset_token, decode_token
from ..credit_ledger import credit as ledger_credit
from ..db import db_session
from ..deps import SESSION_COOKIE, current_user
from ..mail import send_template
from ..models import Session as UserSession, User
from ..security import hash_password, sign_session_id, verify_password
from ..settings import Settings, get_settings
```

Replace the `Credentials` model with a separate `SignupRequest` and a renamed login model:

```python
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


class SignupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
```

Replace the `@router.post("/signup", ...)` function with:

```python
@router.post("/signup", status_code=201)
def signup(body: SignupRequest,
           db: Session = Depends(db_session),
           settings: Settings = Depends(get_settings)):
    if not USERNAME_RE.match(body.username):
        raise HTTPException(422, detail={"error": {"code": "bad_username",
                                                    "message": "username must be 3-32 chars, [a-zA-Z0-9_]"}})
    email = body.email.lower()
    username = body.username.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, detail={"error": {"code": "email_taken",
                                                    "message": "email already registered"}})
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(409, detail={"error": {"code": "username_taken",
                                                    "message": "username already taken"}})

    user = User(
        email=email,
        username=username,
        password_hash=hash_password(body.password),
        email_verified=False,
    )
    db.add(user)
    db.flush()  # so user.id is set

    token = make_verify_token(user.id)
    verify_url = f"{settings.web_origin}/verify?token={token}"
    send_template(email, "verify_email",
                  {"username": user.username, "verify_url": verify_url, "expires_hours": 24},
                  "Confirm your DoThesis email")
    user.last_verify_sent_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "email": email}
```

Replace the existing login function's `Credentials` references with `LoginRequest`:

```python
@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response,
          db: Session = Depends(db_session), settings: Settings = Depends(get_settings)) -> UserOut:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, detail={"error": {"code": "bad_credentials",
                                                    "message": "invalid email or password"}})
    _issue_session(db, user, settings, response, request)
    return _to_out(user)
```

(Login gate logic comes in Task 10 — for this task we just keep the existing behavior so other tests still pass.)

- [ ] **Step 4: Run signup tests**

```
.\.venv\Scripts\python.exe -m pytest tests/test_auth_signup_verify.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/auth.py api/tests/test_auth_signup_verify.py
git commit -m "feat(api): signup takes username + email + password, mails verify link"
```

---

## Task 10: Login gate (block unverified, route Google-only users)

**Files:**
- Modify: `api/app/routers/auth.py`
- Test: `api/tests/test_auth_login_gate.py`

- [ ] **Step 1: Write failing tests**

```python
# api/tests/test_auth_login_gate.py
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import User
from app.security import hash_password


def _client():
    return TestClient(create_app())


def _seed_user(email, *, password="supersecret", verified=False, google_id=None):
    Session = get_session_factory()
    with Session() as s:
        u = User(
            email=email, username=email.split("@")[0],
            password_hash=hash_password(password),
            email_verified=verified,
            google_id=google_id,
        )
        s.add(u)
        s.commit()
        return u


def test_login_unverified_returns_403_with_code():
    _seed_user("alice@e.com", verified=False)
    c = _client()
    r = c.post("/api/v1/auth/login", json={"email": "alice@e.com", "password": "supersecret"})
    assert r.status_code == 403
    body = r.json()
    assert body["detail"]["error"]["code"] == "unverified"
    assert body["detail"]["error"]["email"] == "alice@e.com"


def test_login_verified_succeeds():
    _seed_user("bob@e.com", verified=True)
    c = _client()
    r = c.post("/api/v1/auth/login", json={"email": "bob@e.com", "password": "supersecret"})
    assert r.status_code == 200
    assert "dothesis_session" in c.cookies


def test_login_google_account_bad_password_returns_use_google():
    _seed_user("g@e.com", password="random-throwaway", verified=True, google_id="abc123")
    c = _client()
    r = c.post("/api/v1/auth/login", json={"email": "g@e.com", "password": "wrong-guess"})
    assert r.status_code == 401
    assert r.json()["detail"]["error"]["code"] == "use_google"


def test_login_sets_last_login():
    _seed_user("ll@e.com", verified=True)
    c = _client()
    c.post("/api/v1/auth/login", json={"email": "ll@e.com", "password": "supersecret"})

    Session = get_session_factory()
    with Session() as s:
        u = s.scalar(__import__("sqlalchemy").select(User).where(User.email == "ll@e.com"))
        assert u.last_login is not None
```

- [ ] **Step 2: Run, expect fail (no verify gate yet)**

```
.\.venv\Scripts\python.exe -m pytest tests/test_auth_login_gate.py -v
```

- [ ] **Step 3: Rewrite login**

Replace the login handler with:

```python
@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response,
          db: Session = Depends(db_session), settings: Settings = Depends(get_settings)) -> UserOut:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user:
        raise HTTPException(401, detail={"error": {"code": "bad_credentials",
                                                    "message": "invalid email or password"}})
    if not verify_password(body.password, user.password_hash):
        # If this account is linked to Google, surface that hint so the UI can route them.
        if user.google_id:
            raise HTTPException(401, detail={"error": {"code": "use_google",
                                                        "message": "This account is linked to Google"}})
        raise HTTPException(401, detail={"error": {"code": "bad_credentials",
                                                    "message": "invalid email or password"}})
    if not user.email_verified:
        raise HTTPException(403, detail={"error": {"code": "unverified",
                                                    "message": "Please verify your email",
                                                    "email": user.email}})
    user.last_login = datetime.now(timezone.utc)
    _issue_session(db, user, settings, response, request)
    return _to_out(user)
```

- [ ] **Step 4: Run tests**

```
.\.venv\Scripts\python.exe -m pytest tests/test_auth_login_gate.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/auth.py api/tests/test_auth_login_gate.py
git commit -m "feat(api): block unverified login; route Google-only users via use_google code"
```

---

## Task 11: `/verify` endpoint

**Files:**
- Modify: `api/app/routers/auth.py`
- Test: `api/tests/test_auth_verify.py`

- [ ] **Step 1: Write failing tests**

```python
# api/tests/test_auth_verify.py
import time
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.auth_tokens import make_verify_token, make_reset_token
from app.db import get_session_factory
from app.main import create_app
from app.models import CreditTransaction, User
from app.security import hash_password


def _client():
    return TestClient(create_app())


def _seed(email, **kw):
    Session = get_session_factory()
    with Session() as s:
        u = User(email=email, username=email.split("@")[0],
                 password_hash=hash_password("supersecret"), **kw)
        s.add(u)
        s.commit()
        return u.id


def test_verify_flips_flag_and_grants_bonus(monkeypatch):
    monkeypatch.setenv("DOTHESIS_SIGNUP_BONUS_CREDITS", "100")
    from app import settings as sm; sm._settings = None
    uid = _seed("alice@e.com", email_verified=False)
    tok = make_verify_token(uid)

    c = _client()
    r = c.post("/api/v1/auth/verify", json={"token": tok})
    assert r.status_code == 200, r.text

    Session = get_session_factory()
    with Session() as s:
        u = s.get(User, uid)
        assert u.email_verified is True
        assert u.credit == 100
        tx = s.query(CreditTransaction).filter_by(user_id=uid).all()
        assert any(t.reason == "signup_bonus" for t in tx)


def test_verify_is_idempotent():
    uid = _seed("idem@e.com", email_verified=False)
    tok = make_verify_token(uid)
    c = _client()
    r1 = c.post("/api/v1/auth/verify", json={"token": tok})
    assert r1.status_code == 200
    r2 = c.post("/api/v1/auth/verify", json={"token": tok})
    assert r2.status_code == 200

    Session = get_session_factory()
    with Session() as s:
        u = s.get(User, uid)
        tx_count = s.query(CreditTransaction).filter_by(user_id=uid, reason="signup_bonus").count()
        assert tx_count == 1  # no double bonus
        assert u.credit == 100


def test_verify_rejects_reset_token():
    uid = _seed("x@e.com", email_verified=False)
    tok = make_reset_token(uid)  # wrong kind
    c = _client()
    r = c.post("/api/v1/auth/verify", json={"token": tok})
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] in {"token_invalid", "token_mismatch"}


def test_verify_rejects_garbage_token():
    c = _client()
    r = c.post("/api/v1/auth/verify", json={"token": "not-a-real-token"})
    assert r.status_code == 400
```

- [ ] **Step 2: Run, expect fail**

```
.\.venv\Scripts\python.exe -m pytest tests/test_auth_verify.py -v
```

- [ ] **Step 3: Add the endpoint**

Append to `api/app/routers/auth.py`:

```python
class TokenRequest(BaseModel):
    token: str


@router.post("/verify")
def verify(body: TokenRequest, request: Request, response: Response,
           db: Session = Depends(db_session), settings: Settings = Depends(get_settings)):
    try:
        uid = decode_token(body.token, kind="verify", max_age=VERIFY_TTL)
    except ValueError as e:
        code = str(e) if str(e) in {"token_expired", "token_invalid", "token_mismatch"} else "token_invalid"
        raise HTTPException(400, detail={"error": {"code": code,
                                                    "message": "Verification link is invalid or expired"}})
    user = db.get(User, uid)
    if not user:
        raise HTTPException(400, detail={"error": {"code": "token_invalid",
                                                    "message": "User not found"}})
    if user.email_verified:
        # Already verified — return 200 idempotently; do NOT grant bonus again.
        _issue_session(db, user, settings, response, request)
        return {"ok": True, "already_verified": True, "user": _to_out(user).model_dump()}

    user.email_verified = True
    ledger_credit(db, user, delta=settings.signup_bonus_credits,
                  reason="signup_bonus", ref_type="user", ref_id=user.id)
    user.last_login = datetime.now(timezone.utc)
    _issue_session(db, user, settings, response, request)
    db.commit()
    return {"ok": True, "user": _to_out(user).model_dump()}
```

- [ ] **Step 4: Run tests**

```
.\.venv\Scripts\python.exe -m pytest tests/test_auth_verify.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/auth.py api/tests/test_auth_verify.py
git commit -m "feat(api): /verify endpoint flips email_verified + grants bonus credits"
```

---

## Task 12: `/resend-verification`

**Files:**
- Modify: `api/app/routers/auth.py`
- Test: `api/tests/test_auth_resend.py`

- [ ] **Step 1: Write failing tests**

```python
# api/tests/test_auth_resend.py
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import User
from app.security import hash_password


def _client():
    return TestClient(create_app())


def _seed(email, **kw):
    Session = get_session_factory()
    with Session() as s:
        u = User(email=email, username=email.split("@")[0],
                 password_hash=hash_password("supersecret"), **kw)
        s.add(u); s.commit(); return u.id


def test_resend_for_unknown_email_is_ok_no_enumeration():
    c = _client()
    with patch("app.routers.auth.send_template", return_value=True) as ms:
        r = c.post("/api/v1/auth/resend-verification", json={"email": "ghost@e.com"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    ms.assert_not_called()


def test_resend_for_verified_user_is_ok_no_send():
    _seed("done@e.com", email_verified=True)
    c = _client()
    with patch("app.routers.auth.send_template", return_value=True) as ms:
        r = c.post("/api/v1/auth/resend-verification", json={"email": "done@e.com"})
    assert r.status_code == 200
    ms.assert_not_called()


def test_resend_sends_when_not_verified():
    _seed("u@e.com", email_verified=False)
    c = _client()
    with patch("app.routers.auth.send_template", return_value=True) as ms:
        r = c.post("/api/v1/auth/resend-verification", json={"email": "u@e.com"})
    assert r.status_code == 200
    ms.assert_called_once()


def test_resend_throttled_within_60s():
    uid = _seed("t@e.com", email_verified=False,
                 last_verify_sent_at=datetime.now(timezone.utc))
    c = _client()
    with patch("app.routers.auth.send_template", return_value=True) as ms:
        r = c.post("/api/v1/auth/resend-verification", json={"email": "t@e.com"})
    assert r.status_code == 429
    assert r.json()["detail"]["error"]["code"] == "throttled"
    ms.assert_not_called()


def test_resend_works_after_60s():
    uid = _seed("over@e.com", email_verified=False,
                 last_verify_sent_at=datetime.now(timezone.utc) - timedelta(seconds=70))
    c = _client()
    with patch("app.routers.auth.send_template", return_value=True) as ms:
        r = c.post("/api/v1/auth/resend-verification", json={"email": "over@e.com"})
    assert r.status_code == 200
    ms.assert_called_once()
```

- [ ] **Step 2: Run, expect fail**

```
.\.venv\Scripts\python.exe -m pytest tests/test_auth_resend.py -v
```

- [ ] **Step 3: Add the endpoint**

Append to `api/app/routers/auth.py`:

```python
class EmailRequest(BaseModel):
    email: EmailStr


RESEND_THROTTLE_SECONDS = 60


@router.post("/resend-verification")
def resend_verification(body: EmailRequest,
                        db: Session = Depends(db_session),
                        settings: Settings = Depends(get_settings)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or user.email_verified:
        return {"ok": True}  # no enumeration
    now = datetime.now(timezone.utc)
    if user.last_verify_sent_at:
        last = user.last_verify_sent_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        elapsed = (now - last).total_seconds()
        if elapsed < RESEND_THROTTLE_SECONDS:
            raise HTTPException(429, detail={"error": {
                "code": "throttled",
                "message": "Please wait before requesting another email",
                "retry_in": int(RESEND_THROTTLE_SECONDS - elapsed),
            }})
    token = make_verify_token(user.id)
    verify_url = f"{settings.web_origin}/verify?token={token}"
    send_template(user.email, "verify_email",
                  {"username": user.username, "verify_url": verify_url, "expires_hours": 24},
                  "Confirm your DoThesis email")
    user.last_verify_sent_at = now
    db.commit()
    return {"ok": True}
```

- [ ] **Step 4: Run tests**

```
.\.venv\Scripts\python.exe -m pytest tests/test_auth_resend.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/auth.py api/tests/test_auth_resend.py
git commit -m "feat(api): /resend-verification with 60s throttle and no enumeration"
```

---

## Task 13: `/forgot-password`

**Files:**
- Modify: `api/app/routers/auth.py`
- Test: `api/tests/test_auth_password_reset.py`

- [ ] **Step 1: Write failing tests (first half — forgot only)**

Create `api/tests/test_auth_password_reset.py`:

```python
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.auth_tokens import make_reset_token, make_verify_token
from app.db import get_session_factory
from app.main import create_app
from app.models import Session as UserSession, User
from app.security import hash_password, verify_password


def _client():
    return TestClient(create_app())


def _seed(email, **kw):
    Session = get_session_factory()
    with Session() as s:
        u = User(email=email, username=email.split("@")[0],
                 password_hash=hash_password("oldpass1234"),
                 email_verified=True, **kw)
        s.add(u); s.commit(); return u.id


def test_forgot_unknown_email_returns_ok_no_send():
    c = _client()
    with patch("app.routers.auth.send_template", return_value=True) as ms:
        r = c.post("/api/v1/auth/forgot-password", json={"email": "ghost@e.com"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    ms.assert_not_called()


def test_forgot_known_email_sends_template():
    _seed("alice@e.com")
    c = _client()
    with patch("app.routers.auth.send_template", return_value=True) as ms:
        r = c.post("/api/v1/auth/forgot-password", json={"email": "alice@e.com"})
    assert r.status_code == 200
    ms.assert_called_once()
    args, kwargs = ms.call_args
    # send_template(to, template, vars, subject)
    assert args[0] == "alice@e.com"
    assert args[1] == "reset_password"
    assert "reset_url" in args[2]
```

- [ ] **Step 2: Run, expect fail**

```
.\.venv\Scripts\python.exe -m pytest tests/test_auth_password_reset.py -v
```

- [ ] **Step 3: Add the endpoint**

Append to `api/app/routers/auth.py`:

```python
@router.post("/forgot-password")
def forgot_password(body: EmailRequest,
                    db: Session = Depends(db_session),
                    settings: Settings = Depends(get_settings)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user:
        return {"ok": True}  # no enumeration
    token = make_reset_token(user.id)
    reset_url = f"{settings.web_origin}/reset-password?token={token}"
    send_template(user.email, "reset_password",
                  {"username": user.username, "reset_url": reset_url, "expires_minutes": 60},
                  "Reset your DoThesis password")
    return {"ok": True}
```

- [ ] **Step 4: Run tests**

```
.\.venv\Scripts\python.exe -m pytest tests/test_auth_password_reset.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/auth.py api/tests/test_auth_password_reset.py
git commit -m "feat(api): /forgot-password mails reset link without enumeration"
```

---

## Task 14: `/reset-password`

**Files:**
- Modify: `api/app/routers/auth.py`
- Modify: `api/tests/test_auth_password_reset.py` (append)

- [ ] **Step 1: Append failing tests**

Open `api/tests/test_auth_password_reset.py` and add:

```python
def test_reset_with_valid_token_changes_password_and_invalidates_sessions():
    Session = get_session_factory()
    uid = _seed("alice@e.com")
    # Seed a session row so we can verify it gets deleted
    with Session() as s:
        from datetime import datetime, timedelta, timezone
        s.add(UserSession(user_id=uid,
                          expires_at=datetime.now(timezone.utc) + timedelta(days=30)))
        s.commit()
        assert s.query(UserSession).filter_by(user_id=uid).count() == 1

    tok = make_reset_token(uid)
    c = _client()
    r = c.post("/api/v1/auth/reset-password",
                json={"token": tok, "new_password": "brandnew1234"})
    assert r.status_code == 200

    with Session() as s:
        u = s.get(User, uid)
        assert verify_password("brandnew1234", u.password_hash)
        assert not verify_password("oldpass1234", u.password_hash)
        assert s.query(UserSession).filter_by(user_id=uid).count() == 0


def test_reset_rejects_verify_token():
    uid = _seed("x@e.com")
    tok = make_verify_token(uid)
    c = _client()
    r = c.post("/api/v1/auth/reset-password",
                json={"token": tok, "new_password": "supernew1234"})
    assert r.status_code == 400


def test_reset_rejects_short_password():
    uid = _seed("p@e.com")
    tok = make_reset_token(uid)
    c = _client()
    r = c.post("/api/v1/auth/reset-password",
                json={"token": tok, "new_password": "short"})
    assert r.status_code == 422
```

- [ ] **Step 2: Run, expect fail**

```
.\.venv\Scripts\python.exe -m pytest tests/test_auth_password_reset.py -v
```

- [ ] **Step 3: Add the endpoint**

Append to `api/app/routers/auth.py`:

```python
class ResetRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=200)


@router.post("/reset-password")
def reset_password(body: ResetRequest,
                   db: Session = Depends(db_session)):
    try:
        uid = decode_token(body.token, kind="reset", max_age=RESET_TTL)
    except ValueError as e:
        code = str(e) if str(e) in {"token_expired", "token_invalid", "token_mismatch"} else "token_invalid"
        raise HTTPException(400, detail={"error": {"code": code,
                                                    "message": "Reset link is invalid or expired"}})
    user = db.get(User, uid)
    if not user:
        raise HTTPException(400, detail={"error": {"code": "token_invalid",
                                                    "message": "User not found"}})
    user.password_hash = hash_password(body.new_password)
    # Invalidate every existing session for this user
    db.query(UserSession).filter(UserSession.user_id == uid).delete()
    db.commit()
    return {"ok": True}
```

- [ ] **Step 4: Run tests**

```
.\.venv\Scripts\python.exe -m pytest tests/test_auth_password_reset.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/auth.py api/tests/test_auth_password_reset.py
git commit -m "feat(api): /reset-password updates password and invalidates sessions"
```

---

## Task 15: `/google`

**Files:**
- Modify: `api/app/routers/auth.py`
- Test: `api/tests/test_auth_google.py`

- [ ] **Step 1: Write failing tests**

```python
# api/tests/test_auth_google.py
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import CreditTransaction, User
from app.security import hash_password


def _client():
    return TestClient(create_app())


def test_google_first_signin_creates_user_with_bonus(monkeypatch):
    monkeypatch.setenv("DOTHESIS_SIGNUP_BONUS_CREDITS", "100")
    monkeypatch.setenv("DOTHESIS_GOOGLE_CLIENT_ID", "test-id")
    from app import settings as sm; sm._settings = None

    fake_info = {"email": "new@gmail.com", "google_id": "g_99", "name": "New User"}
    with patch("app.routers.auth.verify_google_id_token", return_value=fake_info):
        c = _client()
        r = c.post("/api/v1/auth/google", json={"id_token": "FAKE"})
    assert r.status_code == 200, r.text
    assert "dothesis_session" in c.cookies

    Session = get_session_factory()
    with Session() as s:
        u = s.scalar(__import__("sqlalchemy").select(User).where(User.email == "new@gmail.com"))
        assert u is not None
        assert u.email_verified is True
        assert u.google_id == "g_99"
        assert u.credit == 100
        bonus = s.query(CreditTransaction).filter_by(user_id=u.id, reason="signup_bonus").count()
        assert bonus == 1


def test_google_links_existing_email_account():
    Session = get_session_factory()
    with Session() as s:
        existing = User(email="alice@e.com", username="alice",
                         password_hash=hash_password("supersecret"),
                         email_verified=False)
        s.add(existing); s.commit()
        eid = existing.id

    fake_info = {"email": "alice@e.com", "google_id": "g_77", "name": "Alice"}
    with patch("app.routers.auth.verify_google_id_token", return_value=fake_info):
        c = _client()
        r = c.post("/api/v1/auth/google", json={"id_token": "FAKE"})
    assert r.status_code == 200
    with Session() as s:
        u = s.get(User, eid)
        assert u.google_id == "g_77"
        assert u.email_verified is True


def test_google_returning_user_just_logs_in():
    Session = get_session_factory()
    with Session() as s:
        existing = User(email="bob@e.com", username="bob",
                         password_hash=hash_password("xxxxxxxx"),
                         email_verified=True, google_id="g_55")
        s.add(existing); s.commit()
        eid = existing.id
        existing_count = s.query(CreditTransaction).filter_by(user_id=eid).count()

    fake_info = {"email": "bob@e.com", "google_id": "g_55", "name": "Bob"}
    with patch("app.routers.auth.verify_google_id_token", return_value=fake_info):
        c = _client()
        r = c.post("/api/v1/auth/google", json={"id_token": "FAKE"})
    assert r.status_code == 200
    with Session() as s:
        new_count = s.query(CreditTransaction).filter_by(user_id=eid).count()
        assert new_count == existing_count  # no double bonus


def test_google_bad_token_returns_401():
    with patch("app.routers.auth.verify_google_id_token", side_effect=ValueError("bad")):
        c = _client()
        r = c.post("/api/v1/auth/google", json={"id_token": "BAD"})
    assert r.status_code == 401
    assert r.json()["detail"]["error"]["code"] == "bad_google_token"
```

- [ ] **Step 2: Run, expect fail**

```
.\.venv\Scripts\python.exe -m pytest tests/test_auth_google.py -v
```

- [ ] **Step 3: Add the endpoint**

Add this import near the top of `api/app/routers/auth.py`:

```python
from ..google_auth import verify_google_id_token
```

And append the endpoint:

```python
class GoogleRequest(BaseModel):
    id_token: str


@router.post("/google")
def google_signin(body: GoogleRequest, request: Request, response: Response,
                  db: Session = Depends(db_session),
                  settings: Settings = Depends(get_settings)) -> UserOut:
    try:
        info = verify_google_id_token(body.id_token)
    except ValueError as e:
        raise HTTPException(401, detail={"error": {"code": "bad_google_token",
                                                    "message": str(e)}})

    # 1. Look up by google_id
    user = db.scalar(select(User).where(User.google_id == info["google_id"]))
    # 2. Else by email — link to this Google account
    if not user:
        user = db.scalar(select(User).where(User.email == info["email"]))
        if user:
            user.google_id = info["google_id"]
            if not user.email_verified:
                user.email_verified = True
    # 3. Else create new
    created = False
    if not user:
        import random, secrets
        email_prefix = re.sub(r"[^a-zA-Z0-9]", "", info["email"].split("@")[0])[:24] or "user"
        for _ in range(20):
            candidate = f"{email_prefix}{random.randint(1000, 9999)}"
            if not db.scalar(select(User).where(User.username == candidate)):
                break
        else:
            raise HTTPException(500, detail={"error": {"code": "username_collision",
                                                        "message": "couldn't allocate a unique username"}})
        user = User(
            email=info["email"],
            username=candidate,
            password_hash=hash_password(secrets.token_urlsafe(32)),  # unusable for password login
            email_verified=True,
            google_id=info["google_id"],
        )
        db.add(user)
        db.flush()
        created = True

    if created:
        ledger_credit(db, user, delta=settings.signup_bonus_credits,
                      reason="signup_bonus", ref_type="user", ref_id=user.id)
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    _issue_session(db, user, settings, response, request)
    return _to_out(user)
```

- [ ] **Step 4: Run tests**

```
.\.venv\Scripts\python.exe -m pytest tests/test_auth_google.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/auth.py api/tests/test_auth_google.py
git commit -m "feat(api): /google verifies id_token, finds-or-links-or-creates user"
```

---

## Task 16: Update web proxy PUBLIC_PATHS

**Files:**
- Modify: `web/proxy.js`

- [ ] **Step 1: Add four routes**

In `web/proxy.js`, replace the `PUBLIC_PATHS` line with:

```js
const PUBLIC_PATHS = [
  "/login", "/signup",
  "/verify", "/wait-verify",
  "/forgot-password", "/reset-password",
  "/_next", "/favicon.ico",
];
```

- [ ] **Step 2: Commit**

```bash
git add web/proxy.js
git commit -m "feat(web): allow unauthenticated access to verify/reset/forgot pages"
```

---

## Task 17: `GoogleSignInButton.tsx`

**Files:**
- Create: `web/app/components/auth/GoogleSignInButton.tsx`

- [ ] **Step 1: Write the component**

```tsx
"use client";
import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

import { apiFetch } from "@/app/lib/api";

const CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";

declare global {
  interface Window {
    google?: any;
  }
}

export function GoogleSignInButton({ onError }: { onError?: (msg: string) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();

  useEffect(() => {
    if (!CLIENT_ID) return;
    let script = document.querySelector<HTMLScriptElement>('script[src="https://accounts.google.com/gsi/client"]');
    let added = false;
    if (!script) {
      script = document.createElement("script");
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.defer = true;
      document.body.appendChild(script);
      added = true;
    }
    const init = () => {
      if (!window.google?.accounts?.id || !ref.current) return;
      window.google.accounts.id.initialize({
        client_id: CLIENT_ID,
        callback: async (resp: any) => {
          try {
            await apiFetch("/auth/google", { method: "POST", body: { id_token: resp.credential } });
            router.push("/");
          } catch (e: any) {
            onError?.(e?.body?.detail?.error?.message || e?.message || "Google sign-in failed");
          }
        },
      });
      window.google.accounts.id.renderButton(ref.current, {
        theme: "outline", size: "large", width: 320, shape: "rectangular",
      });
    };
    if (window.google?.accounts?.id) {
      init();
    } else {
      script.onload = init;
    }
    return () => {
      // Don't remove the script — other components may be using it.
      if (added) { /* no-op */ }
    };
  }, [router, onError]);

  if (!CLIENT_ID) {
    return (
      <button
        type="button"
        disabled
        className="w-full rounded-xl border border-ink-200 px-4 py-2.5 text-sm font-medium text-ink-400 cursor-not-allowed"
        title="DOTHESIS_GOOGLE_CLIENT_ID is not set"
      >
        Google sign-in (not configured)
      </button>
    );
  }
  return <div ref={ref} className="flex justify-center" />;
}
```

- [ ] **Step 2: Type-check**

Run from `web/`: `npx tsc --noEmit`. Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add web/app/components/auth/GoogleSignInButton.tsx
git commit -m "feat(web): GoogleSignInButton wraps GSI script + /auth/google call"
```

---

## Task 18: Rewrite signup page

**Files:**
- Modify: `web/app/signup/page.jsx`

- [ ] **Step 1: Replace the file**

Overwrite `web/app/signup/page.jsx` with:

```jsx
"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { GoogleSignInButton } from "../components/auth/GoogleSignInButton";
import { apiFetch } from "../lib/api";

const USERNAME_RE = /^[a-zA-Z0-9_]{3,32}$/;

export default function SignupPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    if (!USERNAME_RE.test(username)) {
      setError("Username must be 3–32 characters, letters/numbers/underscore only.");
      return;
    }
    setBusy(true);
    try {
      await apiFetch("/auth/signup", { method: "POST", body: { username, email, password } });
      router.push(`/wait-verify?email=${encodeURIComponent(email)}`);
    } catch (err) {
      const code = err?.body?.detail?.error?.code;
      const map = {
        email_taken: "That email is already registered. Try signing in instead.",
        username_taken: "That username is taken. Pick another.",
        bad_username: "Username must be 3–32 characters, letters/numbers/underscore only.",
      };
      setError(map[code] || err.message || "Signup failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center bg-ink-50 px-4 py-12">
      <div className="w-full max-w-md bg-white rounded-2xl border border-ink-100 shadow-sm p-8 space-y-5">
        <div className="text-center">
          <div className="font-extrabold text-2xl text-ink-900">Do<span className="text-primary-600">Thesis</span></div>
          <h1 className="mt-3 text-xl font-bold text-ink-900">Create your account</h1>
          <p className="mt-1 text-sm text-ink-500">Sign up to start drafting verified-citation theses.</p>
        </div>

        <GoogleSignInButton onError={setError} />

        <div className="flex items-center gap-3 text-xs text-ink-400">
          <span className="flex-1 h-px bg-ink-100" />
          <span>or with email</span>
          <span className="flex-1 h-px bg-ink-100" />
        </div>

        <form onSubmit={submit} className="space-y-3">
          <label className="block">
            <span className="text-xs font-medium text-ink-500">Username</span>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
              className="mt-1 w-full rounded-xl border border-ink-200 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
              placeholder="your_handle"
              pattern="[a-zA-Z0-9_]{3,32}"
            />
          </label>
          <label className="block">
            <span className="text-xs font-medium text-ink-500">Email</span>
            <input
              type="email" value={email} onChange={(e) => setEmail(e.target.value)} required
              className="mt-1 w-full rounded-xl border border-ink-200 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
            />
          </label>
          <label className="block">
            <span className="text-xs font-medium text-ink-500">Password (8+ chars)</span>
            <input
              type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8}
              className="mt-1 w-full rounded-xl border border-ink-200 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
            />
          </label>
          {error && <div className="text-xs text-red-700">{error}</div>}
          <button
            type="submit" disabled={busy}
            className="w-full rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 disabled:opacity-50"
          >
            {busy ? "Creating account…" : "Create account"}
          </button>
        </form>

        <div className="text-center text-sm text-ink-500">
          Already have an account?{" "}
          <Link href="/login" className="text-primary-600 font-medium hover:underline">Sign in</Link>
        </div>
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Type-check**

`npx tsc --noEmit`. Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add web/app/signup/page.jsx
git commit -m "feat(web): signup page with username, Tailwind layout, Google button"
```

---

## Task 19: Rewrite login page

**Files:**
- Modify: `web/app/login/page.jsx`

- [ ] **Step 1: Replace the file**

```jsx
"use client";
import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { GoogleSignInButton } from "../components/auth/GoogleSignInButton";
import { apiFetch } from "../lib/api";
import { useAuth } from "../lib/auth-context";

function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") || "/";
  const resetOk = params.get("reset") === "success";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [unverifiedEmail, setUnverifiedEmail] = useState(null);
  const [busy, setBusy] = useState(false);
  const [resending, setResending] = useState(false);
  const [resendNote, setResendNote] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setUnverifiedEmail(null);
    setBusy(true);
    try {
      await login(email, password);
      router.push(next);
    } catch (err) {
      const code = err?.body?.detail?.error?.code;
      if (code === "unverified") {
        setUnverifiedEmail(err.body.detail.error.email || email);
      } else if (code === "use_google") {
        setError("This email is linked to Google. Use the Google button above.");
      } else {
        setError(err.message || "Login failed.");
      }
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    if (!unverifiedEmail) return;
    setResending(true);
    setResendNote(null);
    try {
      await apiFetch("/auth/resend-verification", { method: "POST", body: { email: unverifiedEmail } });
      setResendNote("Sent. Check your inbox.");
    } catch (e) {
      setResendNote(e.message || "Could not send.");
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="w-full max-w-md bg-white rounded-2xl border border-ink-100 shadow-sm p-8 space-y-5">
      <div className="text-center">
        <div className="font-extrabold text-2xl text-ink-900">Do<span className="text-primary-600">Thesis</span></div>
        <h1 className="mt-3 text-xl font-bold text-ink-900">Sign in</h1>
        <p className="mt-1 text-sm text-ink-500">Continue to your draft workspace.</p>
      </div>

      {resetOk && (
        <div className="rounded-xl border border-green-200 bg-green-50 px-3 py-2 text-xs text-green-700">
          Password updated. Sign in with your new password.
        </div>
      )}

      <GoogleSignInButton onError={setError} />

      <div className="flex items-center gap-3 text-xs text-ink-400">
        <span className="flex-1 h-px bg-ink-100" />
        <span>or with email</span>
        <span className="flex-1 h-px bg-ink-100" />
      </div>

      <form onSubmit={submit} className="space-y-3">
        <label className="block">
          <span className="text-xs font-medium text-ink-500">Email</span>
          <input
            type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus
            className="mt-1 w-full rounded-xl border border-ink-200 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
          />
        </label>
        <label className="block">
          <span className="text-xs font-medium text-ink-500">Password</span>
          <input
            type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8}
            className="mt-1 w-full rounded-xl border border-ink-200 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
          />
        </label>

        {unverifiedEmail && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800 space-y-2">
            <div>
              We sent a verification link to <b>{unverifiedEmail}</b>. Click it to finish signing in.
            </div>
            <button type="button" onClick={resend} disabled={resending}
                    className="rounded-md border border-amber-300 bg-white px-2 py-1 font-semibold text-amber-800 hover:bg-amber-100">
              {resending ? "Sending…" : "Resend email"}
            </button>
            {resendNote && <div>{resendNote}</div>}
          </div>
        )}
        {error && <div className="text-xs text-red-700">{error}</div>}

        <button type="submit" disabled={busy}
                className="w-full rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 disabled:opacity-50">
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <div className="flex justify-between text-xs">
          <Link href="/forgot-password" className="text-primary-600 hover:underline">Forgot password?</Link>
          <Link href="/signup" className="text-primary-600 hover:underline">Create account</Link>
        </div>
      </form>
    </div>
  );
}

export default function LoginPage() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-ink-50 px-4 py-12">
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </main>
  );
}
```

- [ ] **Step 2: Type-check**

`npx tsc --noEmit`. Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add web/app/login/page.jsx
git commit -m "feat(web): login page in Tailwind, Google button, unverified banner + resend"
```

---

## Task 20: Wait-verify page

**Files:**
- Create: `web/app/wait-verify/page.jsx`

- [ ] **Step 1: Write the page**

```jsx
"use client";
import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { apiFetch } from "../lib/api";

function WaitVerifyInner() {
  const params = useSearchParams();
  const email = params.get("email") || "your email";
  const [cooldown, setCooldown] = useState(0);
  const [sending, setSending] = useState(false);
  const [note, setNote] = useState(null);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  const resend = async () => {
    setSending(true);
    setNote(null);
    try {
      await apiFetch("/auth/resend-verification", { method: "POST", body: { email } });
      setNote("Sent. Check your inbox (and spam folder).");
      setCooldown(60);
    } catch (err) {
      const retry = err?.body?.detail?.error?.retry_in;
      if (retry) {
        setCooldown(retry);
        setNote(`Please wait ${retry}s before requesting another.`);
      } else {
        setNote(err.message || "Could not send.");
      }
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="w-full max-w-md bg-white rounded-2xl border border-ink-100 shadow-sm p-8 text-center space-y-4">
      <div className="font-extrabold text-2xl text-ink-900">Do<span className="text-primary-600">Thesis</span></div>
      <div className="text-4xl">📬</div>
      <h1 className="text-xl font-bold text-ink-900">Check your inbox</h1>
      <p className="text-sm text-ink-500">
        We sent a verification link to <b className="text-ink-900">{email}</b>. Click it to finish creating your account.
      </p>
      <button
        type="button" onClick={resend} disabled={sending || cooldown > 0}
        className="rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 disabled:opacity-50"
      >
        {sending ? "Sending…" : cooldown > 0 ? `Resend in ${cooldown}s` : "Resend email"}
      </button>
      {note && <div className="text-xs text-ink-500">{note}</div>}
      <div className="pt-4 text-xs text-ink-500">
        Used the wrong email? <Link href="/signup" className="text-primary-600 font-medium hover:underline">Start over</Link>
      </div>
    </div>
  );
}

export default function WaitVerifyPage() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-ink-50 px-4 py-12">
      <Suspense fallback={null}>
        <WaitVerifyInner />
      </Suspense>
    </main>
  );
}
```

- [ ] **Step 2: Type-check**

`npx tsc --noEmit`. Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add web/app/wait-verify/page.jsx
git commit -m "feat(web): wait-verify page with resend button and cooldown"
```

---

## Task 21: Verify page

**Files:**
- Create: `web/app/verify/page.jsx`

- [ ] **Step 1: Write the page**

```jsx
"use client";
import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { apiFetch } from "../lib/api";

function VerifyInner() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get("token") || "";
  const [state, setState] = useState("pending"); // pending | success | error
  const [errorMsg, setErrorMsg] = useState(null);

  useEffect(() => {
    if (!token) {
      setState("error");
      setErrorMsg("This verification link is missing the token.");
      return;
    }
    apiFetch("/auth/verify", { method: "POST", body: { token } })
      .then(() => {
        setState("success");
        setTimeout(() => router.push("/"), 1800);
      })
      .catch((err) => {
        const code = err?.body?.detail?.error?.code;
        const map = {
          token_expired: "This link has expired. Request a new verification email below.",
          token_invalid: "This link is invalid.",
          token_mismatch: "This link is not a verification link.",
        };
        setErrorMsg(map[code] || err.message || "Verification failed.");
        setState("error");
      });
  }, [token, router]);

  return (
    <div className="w-full max-w-md bg-white rounded-2xl border border-ink-100 shadow-sm p-8 text-center space-y-4">
      <div className="font-extrabold text-2xl text-ink-900">Do<span className="text-primary-600">Thesis</span></div>

      {state === "pending" && (
        <>
          <div className="text-2xl">⏳</div>
          <h1 className="text-xl font-bold text-ink-900">Verifying…</h1>
        </>
      )}
      {state === "success" && (
        <>
          <div className="text-4xl">✅</div>
          <h1 className="text-xl font-bold text-ink-900">You're in!</h1>
          <p className="text-sm text-ink-500">Redirecting to your dashboard…</p>
        </>
      )}
      {state === "error" && (
        <>
          <div className="text-4xl">⚠️</div>
          <h1 className="text-xl font-bold text-ink-900">Verification failed</h1>
          <p className="text-sm text-ink-500">{errorMsg}</p>
          <Link href="/login" className="inline-block rounded-xl bg-primary-600 px-4 py-2 text-sm font-semibold text-white">
            Back to sign in
          </Link>
        </>
      )}
    </div>
  );
}

export default function VerifyPage() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-ink-50 px-4 py-12">
      <Suspense fallback={null}>
        <VerifyInner />
      </Suspense>
    </main>
  );
}
```

- [ ] **Step 2: Type-check**

`npx tsc --noEmit`. Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add web/app/verify/page.jsx
git commit -m "feat(web): /verify page (pending → success/redirect or error)"
```

---

## Task 22: Forgot-password page

**Files:**
- Create: `web/app/forgot-password/page.jsx`

- [ ] **Step 1: Write the page**

```jsx
"use client";
import { useState } from "react";
import Link from "next/link";

import { apiFetch } from "../lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/auth/forgot-password", { method: "POST", body: { email } });
      setSent(true);
    } catch (err) {
      setError(err.message || "Could not send reset email.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center bg-ink-50 px-4 py-12">
      <div className="w-full max-w-md bg-white rounded-2xl border border-ink-100 shadow-sm p-8 space-y-5">
        <div className="text-center">
          <div className="font-extrabold text-2xl text-ink-900">Do<span className="text-primary-600">Thesis</span></div>
          <h1 className="mt-3 text-xl font-bold text-ink-900">Forgot your password?</h1>
        </div>

        {sent ? (
          <div className="text-sm text-ink-700 text-center space-y-3">
            <div className="text-3xl">📬</div>
            <p>If that email exists in our system, we sent a reset link. Check your inbox (and spam folder).</p>
            <Link href="/login" className="inline-block text-primary-600 font-medium hover:underline">Back to sign in</Link>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-3">
            <label className="block">
              <span className="text-xs font-medium text-ink-500">Email</span>
              <input
                type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus
                className="mt-1 w-full rounded-xl border border-ink-200 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
              />
            </label>
            {error && <div className="text-xs text-red-700">{error}</div>}
            <button type="submit" disabled={busy}
                    className="w-full rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 disabled:opacity-50">
              {busy ? "Sending…" : "Send reset link"}
            </button>
            <div className="text-center text-xs">
              <Link href="/login" className="text-primary-600 hover:underline">Back to sign in</Link>
            </div>
          </form>
        )}
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Type-check + Commit**

`npx tsc --noEmit`. Expected: clean.

```bash
git add web/app/forgot-password/page.jsx
git commit -m "feat(web): forgot-password page"
```

---

## Task 23: Reset-password page

**Files:**
- Create: `web/app/reset-password/page.jsx`

- [ ] **Step 1: Write the page**

```jsx
"use client";
import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { apiFetch } from "../lib/api";

function ResetInner() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get("token") || "";
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    if (pw !== pw2) {
      setError("Passwords don't match.");
      return;
    }
    if (pw.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      await apiFetch("/auth/reset-password", { method: "POST", body: { token, new_password: pw } });
      router.push("/login?reset=success");
    } catch (err) {
      const code = err?.body?.detail?.error?.code;
      const map = {
        token_expired: "This reset link has expired. Request a new one.",
        token_invalid: "This reset link is invalid.",
        token_mismatch: "This is not a password-reset link.",
      };
      setError(map[code] || err.message || "Reset failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="w-full max-w-md bg-white rounded-2xl border border-ink-100 shadow-sm p-8 space-y-5">
      <div className="text-center">
        <div className="font-extrabold text-2xl text-ink-900">Do<span className="text-primary-600">Thesis</span></div>
        <h1 className="mt-3 text-xl font-bold text-ink-900">Choose a new password</h1>
      </div>
      {!token && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          This page expects a reset token in the URL. Use the link from your email.
        </div>
      )}
      <form onSubmit={submit} className="space-y-3">
        <label className="block">
          <span className="text-xs font-medium text-ink-500">New password (8+ chars)</span>
          <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} required minLength={8} autoFocus
                 className="mt-1 w-full rounded-xl border border-ink-200 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none" />
        </label>
        <label className="block">
          <span className="text-xs font-medium text-ink-500">Confirm password</span>
          <input type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} required minLength={8}
                 className="mt-1 w-full rounded-xl border border-ink-200 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none" />
        </label>
        {error && <div className="text-xs text-red-700">{error}</div>}
        <button type="submit" disabled={busy || !token}
                className="w-full rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 disabled:opacity-50">
          {busy ? "Updating…" : "Update password"}
        </button>
        <div className="text-center text-xs">
          <Link href="/login" className="text-primary-600 hover:underline">Back to sign in</Link>
        </div>
      </form>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-ink-50 px-4 py-12">
      <Suspense fallback={null}>
        <ResetInner />
      </Suspense>
    </main>
  );
}
```

- [ ] **Step 2: Type-check + Commit**

`npx tsc --noEmit`. Expected: clean.

```bash
git add web/app/reset-password/page.jsx
git commit -m "feat(web): reset-password page"
```

---

## Task 24: End-to-end manual verification

- [ ] **Step 1: Set dummy mail mode + a fake Google client id**

Add to `.env`:

```
DOTHESIS_MAIL=dummy
DOTHESIS_GOOGLE_CLIENT_ID=
NEXT_PUBLIC_GOOGLE_CLIENT_ID=
```

(Empty Google client id renders the disabled-button fallback; lets you test the email flows without setting up an OAuth app.)

- [ ] **Step 2: Restart the dev stack**

```bash
./dev.sh
```

- [ ] **Step 3: Run the full backend test suite**

From `api/`:
```
.\.venv\Scripts\python.exe -m pytest tests/test_auth_tokens.py tests/test_mail_dummy.py tests/test_google_auth.py tests/test_auth_signup_verify.py tests/test_auth_login_gate.py tests/test_auth_verify.py tests/test_auth_resend.py tests/test_auth_password_reset.py tests/test_auth_google.py -v
```
Expected: all pass (28+ tests across the new suites).

- [ ] **Step 4: Manual signup → verify**

1. `http://localhost:3000/signup` → enter `alice / alice@example.com / supersecret`.
2. Redirects to `/wait-verify?email=alice@example.com`.
3. Look at the API terminal: a log line `mail dummy mode → to=alice@example.com subject=...` with the rendered HTML. Find the `verify_url`.
4. Paste that URL into the browser. Should show "You're in!" then redirect to `/`.
5. Visit `/credit` — balance should show 100 (the signup bonus).

- [ ] **Step 5: Manual login gate**

1. Sign up another account `bob@example.com` but don't verify.
2. Try `/login` → "We sent a verification link to bob@example.com" banner with "Resend email" button.
3. Click Resend → second click within 60s → banner says "Please wait Ns".

- [ ] **Step 6: Manual forgot/reset**

1. From `/login`, click "Forgot password?".
2. Submit your verified email.
3. From the API terminal, grab the `reset_url`.
4. Paste in browser → new password form → submit → redirects to `/login?reset=success` with green banner.
5. Sign in with the new password.

- [ ] **Step 7: Manual Google flow (optional — only if you set up an OAuth client)**

1. Set `DOTHESIS_GOOGLE_CLIENT_ID=<your.apps.googleusercontent.com>` in `.env`.
2. Set `NEXT_PUBLIC_GOOGLE_CLIENT_ID=<same value>`.
3. Restart the stack.
4. From `/login` or `/signup`, click the rendered Google button.
5. Pick your account in the Google popup.
6. Should land on `/` as a verified user.

- [ ] **Step 8: Commit any tweaks**

If any manual click-through revealed bugs and you patched them, commit. Otherwise skip.

---

## Done criteria

- API: `/api/v1/auth/{signup,login,verify,resend-verification,forgot-password,reset-password,google,logout,me}` all live. Login is gated by `email_verified`. Verifying flips the flag and grants `DOTHESIS_SIGNUP_BONUS_CREDITS` exactly once. Google creates-or-links accounts. Mailer dummy-mode logs HTML when `DOTHESIS_MAIL_FROM` is blank.
- Web: 6 auth pages all in Tailwind. `GoogleSignInButton` renders the GSI button when configured and a disabled placeholder otherwise. Signup → wait-verify → verify → dashboard works end-to-end in dummy-mail mode using terminal logs.
- All new pytest suites pass.

## Out of scope

- Real SES production-access request.
- Apple Sign In, WebAuthn, magic links.
- "Sign out everywhere" UI.
- Marketing emails.
