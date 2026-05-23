from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import db_session
from ..deps import SESSION_COOKIE, current_user
from ..models import Session as UserSession, User
from ..security import hash_password, sign_session_id, verify_password
from ..settings import Settings, get_settings

router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_TTL = timedelta(days=30)


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class UserOut(BaseModel):
    id: str
    email: str
    username: str | None = None
    credit: int = 0
    is_super_admin: bool = False


def _to_out(u: User) -> UserOut:
    from ..admin_config import is_super_admin as _is_admin
    return UserOut(
        id=str(u.id),
        email=u.email,
        username=u.username,
        credit=u.credit,
        is_super_admin=_is_admin(u),
    )


def _issue_session(db: Session, user: User, settings: Settings, response: Response, request: Request) -> None:
    sess = UserSession(
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + SESSION_TTL,
        ip=request.client.host if request.client else None,
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
def signup(creds: Credentials, request: Request, response: Response,
           db: Session = Depends(db_session), settings: Settings = Depends(get_settings)) -> UserOut:
    email = creds.email.lower()
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise HTTPException(409, detail={"error": {"code": "email_taken", "message": "email already registered"}})
    user = User(email=email, password_hash=hash_password(creds.password))
    db.add(user)
    db.commit()
    _issue_session(db, user, settings, response, request)
    return _to_out(user)


@router.post("/login")
def login(creds: Credentials, request: Request, response: Response,
          db: Session = Depends(db_session), settings: Settings = Depends(get_settings)) -> UserOut:
    user = db.scalar(select(User).where(User.email == creds.email.lower()))
    if not user or not verify_password(creds.password, user.password_hash):
        raise HTTPException(401, detail={"error": {"code": "bad_credentials", "message": "invalid email or password"}})
    _issue_session(db, user, settings, response, request)
    return _to_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me")
def me(user: User = Depends(current_user)) -> UserOut:
    return _to_out(user)
