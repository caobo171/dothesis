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

router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_TTL = timedelta(days=30)


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


def _parse_ip(raw: str | None) -> str | None:
    """Return a valid inet string or None (handles test-client hostnames)."""
    import ipaddress
    if not raw:
        return None
    try:
        ipaddress.ip_address(raw)
        return raw
    except ValueError:
        return None


def _issue_session(db: Session, user: User, settings: Settings, response: Response, request: Request) -> None:
    raw_ip = request.client.host if request.client else None
    sess = UserSession(
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + SESSION_TTL,
        ip=_parse_ip(raw_ip),
    )
    db.add(sess)
    db.commit()
    cookie_val = sign_session_id(str(sess.id), secret=settings.session_secret)
    response.set_cookie(
        SESSION_COOKIE,
        cookie_val,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        secure=False,  # set True behind HTTPS in production
        samesite="lax",
        path="/",
    )


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
    return {"ok": True, "email": email}


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response,
          db: Session = Depends(db_session), settings: Settings = Depends(get_settings)) -> UserOut:
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
    _issue_session(db, user, settings, response, request)
    return _to_out(user)


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
        _issue_session(db, user, settings, response, request)
        return {"ok": True, "already_verified": True, "user": _to_out(user).model_dump()}

    user.email_verified = True
    ledger_credit(db, user, delta=settings.signup_bonus_credits,
                  reason="signup_bonus", ref_type="user", ref_id=user.id)
    user.last_login = datetime.now(timezone.utc)
    _issue_session(db, user, settings, response, request)
    db.commit()
    return {"ok": True, "user": _to_out(user).model_dump()}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me")
def me(user: User = Depends(current_user)) -> UserOut:
    return _to_out(user)


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
    db.query(UserSession).filter(UserSession.user_id == uid).delete()
    db.commit()
    return {"ok": True}
