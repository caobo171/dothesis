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
