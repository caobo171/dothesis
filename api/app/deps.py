from datetime import datetime, timezone

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from .db import db_session
from .models import Session as UserSession, User
from .security import verify_session_cookie
from .settings import Settings, get_settings

SESSION_COOKIE = "opendraft_session"


def current_user(
    opendraft_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(db_session),
) -> User:
    if not opendraft_session:
        raise HTTPException(status_code=401, detail={"error": {"code": "unauthenticated", "message": "login required"}})
    try:
        sid = verify_session_cookie(opendraft_session, secret=settings.session_secret)
    except ValueError as e:
        raise HTTPException(status_code=401, detail={"error": {"code": "bad_session", "message": str(e)}})
    sess = db.get(UserSession, sid)
    if sess is None or sess.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail={"error": {"code": "expired", "message": "session expired"}})
    user = db.get(User, sess.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail={"error": {"code": "no_user", "message": "user not found"}})
    return user
