import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rbac import (
    Permission,
    Role,
    RolePermission,
    RoleRequirement,
    UserPlatformRole,
)
from app.models.user import User, UserStatus
from app.repositories.user import active_assignment_clause


class RbacRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_roles(self) -> list[Role]:
        rows = await self.session.scalars(select(Role).order_by(Role.scope, Role.code))
        return list(rows)

    async def list_requirements(self) -> list[RoleRequirement]:
        return list(await self.session.scalars(select(RoleRequirement)))

    async def list_permission_matrix(self) -> list[tuple[Role, Permission, str]]:
        rows = await self.session.execute(
            select(Role, Permission, RolePermission.limit_scope)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .order_by(Permission.code, Role.scope, Role.code)
        )
        return [(role, perm, limit) for role, perm, limit in rows.tuples()]

    async def list_permissions(self) -> list[Permission]:
        return list(await self.session.scalars(select(Permission).order_by(Permission.code)))

    async def get_role(self, scope: str, code: str) -> Role | None:
        return await self.session.scalar(select(Role).where(Role.scope == scope, Role.code == code))

    async def active_platform_assignments(
        self, user_id: uuid.UUID, now: datetime
    ) -> list[tuple[UserPlatformRole, Role]]:
        rows = await self.session.execute(
            select(UserPlatformRole, Role)
            .join(Role, Role.id == UserPlatformRole.role_id)
            .where(UserPlatformRole.user_id == user_id, active_assignment_clause(now))
            .order_by(Role.code)
        )
        return [(assignment, role) for assignment, role in rows.tuples()]

    async def active_assignments_for_users(
        self, user_ids: list[uuid.UUID], now: datetime
    ) -> dict[uuid.UUID, list[tuple[UserPlatformRole, Role]]]:
        result: dict[uuid.UUID, list[tuple[UserPlatformRole, Role]]] = {i: [] for i in user_ids}
        if not user_ids:
            return result
        rows = await self.session.execute(
            select(UserPlatformRole, Role)
            .join(Role, Role.id == UserPlatformRole.role_id)
            .where(UserPlatformRole.user_id.in_(user_ids), active_assignment_clause(now))
            .order_by(Role.code)
        )
        for assignment, role in rows.tuples():
            result[assignment.user_id].append((assignment, role))
        return result

    async def platform_grants(self, user_id: uuid.UUID, now: datetime) -> list[tuple[str, str]]:
        """(permission code, limit) granted through the user's active platform roles."""
        rows = await self.session.execute(
            select(Permission.code, RolePermission.limit_scope)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserPlatformRole, UserPlatformRole.role_id == RolePermission.role_id)
            .where(UserPlatformRole.user_id == user_id, active_assignment_clause(now))
        )
        return [(code, limit) for code, limit in rows.tuples()]

    async def get_assignment(self, assignment_id: uuid.UUID) -> UserPlatformRole | None:
        return await self.session.get(UserPlatformRole, assignment_id)

    async def add_assignment(self, assignment: UserPlatformRole) -> UserPlatformRole:
        self.session.add(assignment)
        await self.session.flush()
        return assignment

    async def count_active_holders(self, role_id: uuid.UUID, now: datetime) -> int:
        """Active users currently holding the role."""
        total = await self.session.scalar(
            select(func.count(func.distinct(UserPlatformRole.user_id)))
            .join(User, User.id == UserPlatformRole.user_id)
            .where(
                UserPlatformRole.role_id == role_id,
                User.status == UserStatus.ACTIVE,
                active_assignment_clause(now),
            )
        )
        return total or 0

    async def expiring_assignments(
        self, now: datetime, until: datetime
    ) -> list[tuple[UserPlatformRole, Role, User]]:
        rows = await self.session.execute(
            select(UserPlatformRole, Role, User)
            .join(Role, Role.id == UserPlatformRole.role_id)
            .join(User, User.id == UserPlatformRole.user_id)
            .where(
                UserPlatformRole.revoked_at.is_(None),
                UserPlatformRole.expires_at > now,
                UserPlatformRole.expires_at <= until,
            )
            .order_by(UserPlatformRole.expires_at)
        )
        return [(a, r, u) for a, r, u in rows.tuples()]
