import time
import pytest
from app.jwt_auth import sign_stream_token, verify_stream_token

SECRET = "x" * 32

def test_roundtrip_ok():
    tok, exp = sign_stream_token("user-1", scope="job:abc", secret=SECRET)
    claims = verify_stream_token(tok, expected_scope="job:abc", secret=SECRET)
    assert claims.user_id == "user-1"
    assert claims.scope == "job:abc"
    assert exp > int(time.time())

def test_wrong_scope_rejected():
    tok, _ = sign_stream_token("user-1", scope="job:abc", secret=SECRET)
    with pytest.raises(ValueError, match="scope"):
        verify_stream_token(tok, expected_scope="job:other", secret=SECRET)

def test_expired_rejected():
    tok, _ = sign_stream_token("u", scope="job:abc", secret=SECRET, ttl_seconds=-1)
    with pytest.raises(ValueError, match="expired"):
        verify_stream_token(tok, expected_scope="job:abc", secret=SECRET)

def test_access_token_not_accepted_as_stream():
    # An ordinary access token (no typ=stream) must not pass stream verification.
    from app.jwt_auth import sign_access_token
    tok, _ = sign_access_token("u", secret=SECRET)
    with pytest.raises(ValueError):
        verify_stream_token(tok, expected_scope="job:abc", secret=SECRET)
