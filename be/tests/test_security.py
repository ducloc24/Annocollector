import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.core.rate_limit import RateLimitedError, SlidingWindowLimiter
from app.core.security import (
    JWT_ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_opaque_token,
    hash_password,
    verify_password,
)


def test_password_hash_round_trip():
    hashed = hash_password("correct horse battery")
    assert hashed != "correct horse battery"
    assert verify_password("correct horse battery", hashed)
    assert not verify_password("wrong password", hashed)


def test_verify_password_without_hash_is_false():
    assert not verify_password("anything", None)
    assert not verify_password("dummy-password-for-timing", None)


def test_access_token_round_trip():
    user_id = uuid.uuid4()
    token = create_access_token(user_id, 3, datetime.now(UTC))
    claims = decode_access_token(token)
    assert claims.user_id == user_id
    assert claims.token_version == 3


def test_expired_access_token():
    token = create_access_token(uuid.uuid4(), 0, datetime.now(UTC) - timedelta(hours=1))
    with pytest.raises(UnauthorizedError) as exc:
        decode_access_token(token)
    assert exc.value.code == "token_expired"


def test_tampered_access_token():
    payload = {
        "sub": str(uuid.uuid4()),
        "ver": 0,
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    forged = jwt.encode(payload, "another-secret-of-sufficient-length-xx", algorithm=JWT_ALGORITHM)
    with pytest.raises(UnauthorizedError) as exc:
        decode_access_token(forged)
    assert exc.value.code == "unauthorized"


def test_access_token_without_version_is_rejected():
    payload = {"sub": str(uuid.uuid4()), "iat": datetime.now(UTC), "exp": datetime.now(UTC)}
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=JWT_ALGORITHM)
    with pytest.raises(UnauthorizedError):
        decode_access_token(token)


def test_opaque_token_hash_is_stable():
    assert hash_opaque_token("abc") == hash_opaque_token("abc")
    assert len(hash_opaque_token("abc")) == 64


def test_rate_limiter_window():
    clock = [0.0]
    limiter = SlidingWindowLimiter(2, clock=lambda: clock[0])
    limiter.hit("k")
    limiter.hit("k")
    with pytest.raises(RateLimitedError):
        limiter.hit("k")
    clock[0] = 61.0
    limiter.hit("k")
    limiter.reset("k")
    limiter.hit("k")
    limiter.hit("k")
