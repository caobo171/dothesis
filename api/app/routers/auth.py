"""Auth router — access-token only, no session cookies.

History: this router used to write `Session` rows and set the
`dothesis_session` cookie via `_issue_session`. That path is gone — see
jwt_auth.py for the rationale. Login / signup / verify / google all return
`{user, access_token, expires_at}` in the response body. The client stores
the token in localStorage and POSTs it in the body of every authenticated
request.

The Session table itself is left in place (not dropped) so existing
migration history stays clean, but no new rows are written.
"""
from datetime import datetime, timezone
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth_tokens import VERIFY_TTL, RESET_TTL, make_verify_token, make_reset_token, decode_token
from ..google_auth import verify_google_id_token
from ..credit_ledger import credit as ledger_credit
from ..db import db_session
from ..deps import current_user
from ..jwt_auth import AuthedBody, sign_access_token, sign_stream_token
from ..mail import send_template
from ..models import User
from ..security import hash_password, verify_password
from ..settings import Settings, get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


class SignupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class UserOut(BaseModel):
    id: str
    email: str
    username: str | None = None
    credit: int = 0
    is_super_admin: bool = False
    created_at: str | None = None


class TokenOut(BaseModel):
    """Wraps the user payload with the issued access token.

    Why expose `expires_at` (epoch seconds) alongside the token: the client
    needs to know when to re-auth without parsing the JWT. Shipping a
    decoder to the browser would be wasteful and expose the algorithm
    choice; one extra integer in the response is cheaper.
    """
    user: UserOut
    access_token: str
    expires_at: int


def _to_out(u: User) -> UserOut:
    from ..admin_config import is_super_admin as _is_admin
    return UserOut(
        id=str(u.id),
        email=u.email,
        username=u.username,
        credit=u.credit,
        is_super_admin=_is_admin(u),
        created_at=u.created_at.isoformat() if u.created_at else None,
    )


def _issue_token(user: User, settings: Settings) -> TokenOut:
    """Build the TokenOut response. No DB writes — JWTs are stateless."""
    token, exp = sign_access_token(str(user.id), secret=settings.session_secret)
    return TokenOut(user=_to_out(user), access_token=token, expires_at=exp)


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
    db.flush()

    token = make_verify_token(user.id)
    verify_url = f"{settings.web_origin}/verify?token={token}"
    send_template(email, "verify_email",
                  {"username": user.username, "verify_url": verify_url, "expires_hours": 24},
                  "Confirm your DoThesis email")
    user.last_verify_sent_at = datetime.now(timezone.utc)
    db.commit()
    # Signup itself doesn't auth the user — they must verify email first.
    # Returning ok+email matches the old contract; the client redirects to
    # the "check your email" screen.
    return {"ok": True, "email": email}


@router.post("/login")
def login(body: LoginRequest,
          db: Session = Depends(db_session),
          settings: Settings = Depends(get_settings)) -> TokenOut:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user:
        raise HTTPException(401, detail={"error": {"code": "bad_credentials",
                                                    "message": "invalid email or password"}})
    if not verify_password(body.password, user.password_hash):
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
    db.commit()
    return _issue_token(user, settings)


class VerifyRequest(BaseModel):
    """Email verification — `token` here is the email-verify token (not an
    access token). The user isn't logged in yet so we can't require
    `access_token`; this body intentionally does NOT inherit from AuthedBody.
    """
    token: str


@router.post("/verify")
def verify(body: VerifyRequest,
           db: Session = Depends(db_session),
           settings: Settings = Depends(get_settings)) -> TokenOut:
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
    if not user.email_verified:
        user.email_verified = True
        ledger_credit(db, user, delta=settings.signup_bonus_credits,
                      reason="signup_bonus", ref_type="user", ref_id=user.id)
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    return _issue_token(user, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout():
    # Stateless tokens — server has nothing to revoke. The client wipes
    # localStorage on its end. Endpoint kept for symmetry with the
    # frontend's logout flow (UX: "logging out…" toast). No body required.
    return None


@router.post("/me")
def me(user: User = Depends(current_user)) -> UserOut:
    # `current_user` reads access_token from body — no need to declare an
    # explicit AuthedBody parameter here. The endpoint still requires a
    # body (empty body → 401).
    return _to_out(user)


class EmailRequest(BaseModel):
    """Email-only requests (resend verification, forgot password) — no
    access token because the user isn't logged in."""
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


@router.post("/forgot-password")
def forgot_password(body: EmailRequest,
                    db: Session = Depends(db_session),
                    settings: Settings = Depends(get_settings)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user:
        return {"ok": True}
    token = make_reset_token(user.id)
    reset_url = f"{settings.web_origin}/reset-password?token={token}"
    send_template(user.email, "reset_password",
                  {"username": user.username, "reset_url": reset_url, "expires_minutes": 60},
                  "Reset your DoThesis password")
    return {"ok": True}


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
    # Note: with stateless JWTs we can't invalidate already-issued tokens
    # here. Old tokens stay valid for up to 7 days. The new password
    # blocks future logins via the old credentials, which is the realistic
    # attack vector; a stolen-then-rotated-password scenario is rare
    # enough to accept until we add a `token_invalidation_after` column
    # on User for hard revocation.
    db.commit()
    return {"ok": True}


class StreamTokenIn(AuthedBody):
    # `scope` names the single resource+action this token may unlock, e.g.
    # "job:<id>". The consuming route re-checks scope against its own path and
    # runs ownership checks, so a mismatched scope just yields a token that
    # opens nothing.
    scope: str = Field(..., min_length=1, max_length=200)


class StreamTokenOut(BaseModel):
    stream_token: str
    expires_at: int


@router.post("/stream-token", response_model=StreamTokenOut)
def mint_stream_token(body: StreamTokenIn,
                      user: User = Depends(current_user),
                      settings: Settings = Depends(get_settings)):
    """Mint a short-lived, resource-scoped token for a browser-GET endpoint
    (SSE / file download) that can't carry the JWT in a body.

    Why a dedicated mint route: EventSource and `<a download>` issue plain GETs
    with no body, so the access_token (which rides in the POST body per
    CLAUDE.md) can't reach them. Instead the client exchanges its access_token
    here for a 120s token bound to ONE scope, then puts that in `?st=`. A leaked
    URL is then useful for ~2 min and only for that one resource.
    """
    tok, exp = sign_stream_token(str(user.id), scope=body.scope,
                                 secret=settings.session_secret)
    return StreamTokenOut(stream_token=tok, expires_at=exp)


class GoogleRequest(BaseModel):
    id_token: str


@router.post("/google")
def google_signin(body: GoogleRequest,
                  db: Session = Depends(db_session),
                  settings: Settings = Depends(get_settings)) -> TokenOut:
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
            password_hash=hash_password(secrets.token_urlsafe(32)),
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
    return _issue_token(user, settings)
