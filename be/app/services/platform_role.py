import uuid
from datetime import datetime, timedelta

from app.core.clock import Clock, utcnow
from app.core.exceptions import (
    AppError,
    ConflictError,
    ForbiddenError,
    InvalidStateError,
    NotFoundError,
)
from app.core.rbac_catalog import ConflictEffect, PlatformRole, RoleScope, platform_conflict
from app.models.rbac import Role, UserPlatformRole
from app.models.user import User, UserStatus
from app.repositories.rbac import RbacRepository
from app.repositories.user import UserRepository
from app.services.audit import AuditService


def assignment_snapshot(assignment: UserPlatformRole, role: Role) -> dict[str, object]:
    return {
        "role": role.code,
        "expires_at": assignment.expires_at.isoformat() if assignment.expires_at else None,
    }


class PlatformRoleService:
    def __init__(
        self,
        users: UserRepository,
        rbac: RbacRepository,
        audit: AuditService,
        clock: Clock = utcnow,
    ) -> None:
        self.users = users
        self.rbac = rbac
        self.audit = audit
        self.clock = clock

    async def grant(
        self,
        actor: User,
        user_id: uuid.UUID,
        role_code: str,
        *,
        expires_at: datetime | None,
        acknowledge_warning: bool = False,
    ) -> tuple[UserPlatformRole, Role]:
        if actor.id == user_id:
            raise ForbiddenError("You cannot grant roles to yourself", code="self_grant_forbidden")
        now = self.clock()
        self._check_expiry(expires_at, now)
        user = await self._active_user(user_id)
        role = await self.rbac.get_role(RoleScope.PLATFORM, role_code)
        if role is None:
            raise NotFoundError("Platform role not found", code="role_not_found")

        held = await self.rbac.active_platform_assignments(user.id, now)
        if any(r.id == role.id for _, r in held):
            raise ConflictError("Role is already granted", code="role_already_granted")
        warnings = []
        for _, other in held:
            effect = platform_conflict(other.code, role.code)
            if effect == ConflictEffect.BLOCK:
                raise ConflictError(
                    "Role conflicts with a role the user holds",
                    code="role_conflict",
                    details={"conflicts_with": other.code},
                )
            if effect == ConflictEffect.WARN:
                warnings.append(other.code)
        if warnings and not acknowledge_warning:
            raise ConflictError(
                "Role should not be combined with a role the user holds; "
                "resend with acknowledge_warning=true to proceed",
                code="role_conflict_warning",
                details={"conflicts_with": warnings},
            )

        assignment = await self.rbac.add_assignment(
            UserPlatformRole(
                id=uuid.uuid4(),
                user_id=user.id,
                role_id=role.id,
                granted_by=actor.id,
                granted_at=now,
                expires_at=expires_at,
            )
        )
        await self.audit.record(
            actor=actor,
            action="platform_role.grant",
            target_type="platform_role",
            target_id=assignment.id,
            after={"user_id": str(user.id), **assignment_snapshot(assignment, role)},
            reason="acknowledged conflict warning" if warnings else None,
        )
        return assignment, role

    async def extend(
        self,
        actor: User,
        user_id: uuid.UUID,
        assignment_id: uuid.UUID,
        expires_at: datetime | None,
    ) -> tuple[UserPlatformRole, Role]:
        if actor.id == user_id:
            raise ForbiddenError("You cannot change your own roles", code="self_grant_forbidden")
        now = self.clock()
        self._check_expiry(expires_at, now)
        assignment, role = await self._active_assignment(user_id, assignment_id)
        before = assignment_snapshot(assignment, role)
        assignment.expires_at = expires_at
        await self.audit.record(
            actor=actor,
            action="platform_role.extend",
            target_type="platform_role",
            target_id=assignment.id,
            before=before,
            after=assignment_snapshot(assignment, role),
        )
        return assignment, role

    async def revoke(
        self, actor: User, user_id: uuid.UUID, assignment_id: uuid.UUID, reason: str
    ) -> None:
        now = self.clock()
        assignment, role = await self._active_assignment(user_id, assignment_id)
        if (
            role.code == PlatformRole.HR_ADMIN
            and await self.rbac.count_active_holders(role.id, now) <= 1
        ):
            raise ConflictError("This is the last active hr_admin", code="last_hr_admin")
        assignment.revoked_at = now
        assignment.revoked_by = actor.id
        assignment.revoke_reason = reason
        # Build step 2: project and team memberships that rely on this role stop applying
        # because the resolver checks role requirements on every request.
        await self.audit.record(
            actor=actor,
            action="platform_role.revoke",
            target_type="platform_role",
            target_id=assignment.id,
            before={"user_id": str(user_id), **assignment_snapshot(assignment, role)},
            reason=reason,
        )

    async def expiring(self, within_days: int) -> list[tuple[UserPlatformRole, Role, User]]:
        now = self.clock()
        return await self.rbac.expiring_assignments(now, now + timedelta(days=within_days))

    async def _active_user(self, user_id: uuid.UUID) -> User:
        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found")
        if user.status != UserStatus.ACTIVE:
            raise InvalidStateError("User is not active", code="account_inactive")
        return user

    async def _active_assignment(
        self, user_id: uuid.UUID, assignment_id: uuid.UUID
    ) -> tuple[UserPlatformRole, Role]:
        for assignment, role in await self.rbac.active_platform_assignments(user_id, self.clock()):
            if assignment.id == assignment_id:
                return assignment, role
        raise NotFoundError("Active role assignment not found")

    @staticmethod
    def _check_expiry(expires_at: datetime | None, now: datetime) -> None:
        if expires_at is not None and expires_at <= now:
            raise AppError("expires_at must be in the future", code="invalid_expiry")
