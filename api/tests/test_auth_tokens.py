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
    tok = make_verify_token(uuid.uuid4())
    time.sleep(2.5)
    with pytest.raises(ValueError):
        decode_token(tok, kind="verify", max_age=1)
