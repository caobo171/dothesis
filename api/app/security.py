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
    """Mint a JWT access token for `user`.

    Kept the function name for back-compat with tests that import it.
    Returns the token string (not a cookie value, not a DB row id) — the
    test rewrite changed `client.cookies.set(...)` to
    `client.headers["Authorization"] = f"Bearer {token}"`.

    `db` is unused now but kept in the signature so old call sites pass
    through unchanged. Will be removed when the test wave that touches
    each call site lands; doing it lazily avoids a 20-file mechanical
    diff that this PR is already mid-stream of.
    """
    from .jwt_auth import sign_access_token
    from .settings import get_settings
    _ = db  # silence linter — see docstring
    token, _exp = sign_access_token(str(user.id), secret=get_settings().session_secret)
    return token
