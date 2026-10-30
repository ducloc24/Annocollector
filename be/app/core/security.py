"""Password hashing, access tokens (JWT) and opaque tokens (refresh, activation)."""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import settings
from app.core.exceptions import UnauthorizedError

JWT_ALGORITHM = "HS256"
MIN_PASSWORD_LENGTH = 10

_hasher = PasswordHasher()
# Verified against when the email is unknown, so both paths cost the same time.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    token_version: int


def create_access_token(user_id: uuid.UUID, token_version: int, now: datetime) -> str:
    payload = {
        "sub": str(user_id),
        "ver": token_version,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_MINUTES),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> AccessClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "ver", "exp", "iat"]},
        )
        return AccessClaims(user_id=uuid.UUID(payload["sub"]), token_version=int(payload["ver"]))
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Access token expired", code="token_expired") from None
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise UnauthorizedError("Invalid access token") from None


def new_opaque_token() -> str:
    """Random token handed to the client; only its hash is stored."""
    return secrets.token_urlsafe(32)


def hash_opaque_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
