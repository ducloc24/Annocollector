import uuid
from dataclasses import dataclass
from datetime import timedelta

from app.core.clock import Clock, utcnow
from app.core.config import settings
from app.core.exceptions import AppError, UnauthorizedError
from app.core.security import (
    MIN_PASSWORD_LENGTH,
    create_access_token,
    decode_access_token,
    hash_opaque_token,
    hash_password,
    new_opaque_token,
    verify_password,
)
from app.models.user import ActionTokenPurpose, RefreshToken, User, UserStatus
from app.repositories.user import TokenRepository, UserRepository
from app.services.audit import AuditService


class WeakPasswordError(AppError):
    code = "password_too_weak"


def validate_new_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
            details={"min_length": MIN_PASSWORD_LENGTH},
        )


@dataclass(frozen=True)
class IssuedTokens:
    user: User
    access_token: str
    refresh_token: str


def _token_revoked() -> UnauthorizedError:
    return UnauthorizedError("Token has been revoked", code="token_revoked")


class AuthService:
    def __init__(
        self,
        users: UserRepository,
        tokens: TokenRepository,
        audit: AuditService,
        clock: Clock = utcnow,
    ) -> None:
        self.users = users
        self.tokens = tokens
        self.audit = audit
        self.clock = clock

    async def authenticate(self, access_token: str) -> User:
        """Resolve the caller from an access token; reject revoked or inactive users."""
        claims = decode_access_token(access_token)
        user = await self.users.get(claims.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise _token_revoked()
        if user.token_version != claims.token_version:
            raise _token_revoked()
        return user

    async def login(
        self, email: str, password: str, *, ip: str | None, user_agent: str | None
    ) -> IssuedTokens:
        user = await self.users.get_by_email(email.strip().lower())
        password_ok = verify_password(password, user.password_hash if user else None)
        if user is None or not password_ok:
            raise UnauthorizedError("Invalid email or password", code="invalid_credentials")
        if user.status != UserStatus.ACTIVE:
            raise UnauthorizedError("Account is not active", code="account_inactive")
        return await self._issue(user, family_id=uuid.uuid4(), ip=ip, user_agent=user_agent)

    async def refresh(
        self, raw_token: str | None, *, ip: str | None, user_agent: str | None
    ) -> IssuedTokens:
        if not raw_token:
            raise UnauthorizedError("Missing refresh token")
        now = self.clock()
        token = await self.tokens.get_refresh_by_hash(hash_opaque_token(raw_token))
        if token is None:
            raise UnauthorizedError("Invalid refresh token")
        if token.revoked_at is not None:
            if token.replaced_by_id is not None:
                # A rotated token came back: assume it was stolen and end the whole chain.
                await self.tokens.revoke_family(token.family_id, now)
            raise _token_revoked()
        if token.expires_at <= now:
            raise UnauthorizedError("Refresh token expired", code="token_expired")
        user = await self.users.get(token.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            await self.tokens.revoke_family(token.family_id, now)
            raise _token_revoked()

        raw, record = await self._new_refresh_token(user, token.family_id, ip, user_agent)
        token.revoked_at = now
        token.replaced_by_id = record.id
        return IssuedTokens(
            user=user,
            access_token=create_access_token(user.id, user.token_version, now),
            refresh_token=raw,
        )

    async def logout(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        token = await self.tokens.get_refresh_by_hash(hash_opaque_token(raw_token))
        if token is not None and token.revoked_at is None:
            token.revoked_at = self.clock()

    async def activate(self, raw_token: str, password: str) -> None:
        now = self.clock()
        token = await self.tokens.get_action_by_hash(hash_opaque_token(raw_token))
        if (
            token is None
            or token.purpose != ActionTokenPurpose.ACTIVATE
            or token.used_at is not None
            or token.expires_at <= now
        ):
            raise AppError("Activation link is invalid or expired", code="invalid_action_token")
        user = await self.users.get(token.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise AppError("Activation link is invalid or expired", code="invalid_action_token")
        validate_new_password(password)
        user.password_hash = hash_password(password)
        token.used_at = now
        await self.audit.record(
            actor=user, action="user.activate", target_type="user", target_id=user.id
        )

    async def change_password(
        self,
        user: User,
        current_password: str,
        new_password: str,
        *,
        ip: str | None,
        user_agent: str | None,
    ) -> IssuedTokens:
        if not verify_password(current_password, user.password_hash):
            raise UnauthorizedError("Current password is incorrect", code="invalid_credentials")
        validate_new_password(new_password)
        user.password_hash = hash_password(new_password)
        # Every other session must sign in again.
        user.token_version += 1
        await self.tokens.revoke_user_refresh_tokens(user.id, self.clock())
        await self.audit.record(
            actor=user, action="user.password_change", target_type="user", target_id=user.id
        )
        return await self._issue(user, family_id=uuid.uuid4(), ip=ip, user_agent=user_agent)

    async def _issue(
        self, user: User, *, family_id: uuid.UUID, ip: str | None, user_agent: str | None
    ) -> IssuedTokens:
        raw, _ = await self._new_refresh_token(user, family_id, ip, user_agent)
        return IssuedTokens(
            user=user,
            access_token=create_access_token(user.id, user.token_version, self.clock()),
            refresh_token=raw,
        )

    async def _new_refresh_token(
        self, user: User, family_id: uuid.UUID, ip: str | None, user_agent: str | None
    ) -> tuple[str, RefreshToken]:
        raw = new_opaque_token()
        record = await self.tokens.add_refresh(
            RefreshToken(
                id=uuid.uuid4(),
                user_id=user.id,
                family_id=family_id,
                token_hash=hash_opaque_token(raw),
                ip=ip,
                user_agent=user_agent[:512] if user_agent else None,
                expires_at=self.clock() + timedelta(days=settings.REFRESH_TOKEN_DAYS),
            )
        )
        return raw, record
