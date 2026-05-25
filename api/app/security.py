import bcrypt
from itsdangerous import BadSignature, Signer


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


def _signer(secret: str) -> Signer:
    return Signer(secret, salt="opendraft-session")


def sign_session_id(session_id: str, *, secret: str) -> str:
    return _signer(secret).sign(session_id.encode()).decode()


def verify_session_cookie(cookie_value: str, *, secret: str) -> str:
    try:
        return _signer(secret).unsign(cookie_value.encode()).decode()
    except BadSignature as e:
        raise ValueError("bad session cookie") from e


def create_session(db, user) -> str:
    """Create a DB session row and return a signed cookie value.

    Convenience helper used by tests to authenticate a client without
    going through the full HTTP signup/login flow.
    """
    from datetime import datetime, timedelta, timezone

    from .models import Session as UserSession
    from .settings import get_settings

    sess = UserSession(
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.add(sess)
    db.commit()
    return sign_session_id(str(sess.id), secret=get_settings().session_secret)
