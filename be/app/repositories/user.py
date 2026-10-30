import uuid
from datetime import datetime

from sqlalchemy import ColumnElement, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rbac import Role, UserPlatformRole
from app.models.user import RefreshToken, User, UserActionToken


def active_assignment_clause(now: datetime) -> ColumnElement[bool]:
    """A platform role assignment that is neither revoked nor expired at ``now``."""
    return (UserPlatformRole.revoked_at.is_(None)) & (
        UserPlatformRole.expires_at.is_(None) | (UserPlatformRole.expires_at > now)
    )


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        return await self.session.scalar(select(User).where(User.email == email))

    async def get_by_employee_code(self, code: str) -> User | None:
        return await self.session.scalar(select(User).where(User.employee_code == code))

    async def add(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        return user

    async def search(
        self,
        *,
        q: str | None,
        status: str | None,
        employment_type: str | None,
        role_code: str | None,
        now: datetime,
        offset: int,
        limit: int,
    ) -> tuple[list[User], int]:
        stmt = select(User)
        if q:
            pattern = f"%{q.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(User.full_name).like(pattern),
                    func.lower(User.email).like(pattern),
                    func.lower(User.employee_code).like(pattern),
                )
            )
        if status:
            stmt = stmt.where(User.status == status)
        if employment_type:
            stmt = stmt.where(User.employment_type == employment_type)
        if role_code:
            stmt = stmt.where(
                select(UserPlatformRole.id)
                .join(Role, Role.id == UserPlatformRole.role_id)
                .where(
                    UserPlatformRole.user_id == User.id,
                    Role.code == role_code,
                    active_assignment_clause(now),
                )
                .exists()
            )
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self.session.scalars(
            stmt.order_by(User.full_name, User.id).offset(offset).limit(limit)
        )
        return list(rows), total or 0


class TokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_refresh(self, token: RefreshToken) -> RefreshToken:
        self.session.add(token)
        await self.session.flush()
        return token

    async def get_refresh_by_hash(self, token_hash: str) -> RefreshToken | None:
        return await self.session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )

    async def revoke_family(self, family_id: uuid.UUID, now: datetime) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    async def revoke_user_refresh_tokens(
        self, user_id: uuid.UUID, now: datetime, *, keep_family: uuid.UUID | None = None
    ) -> None:
        stmt = update(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
        if keep_family is not None:
            stmt = stmt.where(RefreshToken.family_id != keep_family)
        await self.session.execute(stmt.values(revoked_at=now))

    async def add_action_token(self, token: UserActionToken) -> UserActionToken:
        self.session.add(token)
        await self.session.flush()
        return token

    async def get_action_by_hash(self, token_hash: str) -> UserActionToken | None:
        return await self.session.scalar(
            select(UserActionToken).where(UserActionToken.token_hash == token_hash)
        )

    async def close_open_action_tokens(
        self, user_id: uuid.UUID, purpose: str, now: datetime
    ) -> None:
        await self.session.execute(
            update(UserActionToken)
            .where(
                UserActionToken.user_id == user_id,
                UserActionToken.purpose == purpose,
                UserActionToken.used_at.is_(None),
            )
            .values(used_at=now)
        )
