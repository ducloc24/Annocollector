import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.core.clock import Clock, utcnow
from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, InvalidStateError, NotFoundError
from app.core.rbac_catalog import PlatformRole, RoleScope
from app.core.security import hash_opaque_token, new_opaque_token
from app.models.rbac import Role, UserPlatformRole
from app.models.user import ActionTokenPurpose, User, UserActionToken, UserStatus
from app.repositories.rbac import RbacRepository
from app.repositories.user import TokenRepository, UserRepository
from app.repositories.work import WorkRepository
from app.services.audit import AuditService

Assignments = list[tuple[UserPlatformRole, Role]]


@dataclass(frozen=True)
class NewUser:
    email: str
    full_name: str
    employment_type: str
    employee_code: str | None = None
    joined_at: date | None = None


@dataclass(frozen=True)
class ActivationLink:
    url: str
    expires_at: datetime


def user_snapshot(user: User) -> dict[str, object]:
    return {
        "email": user.email,
        "full_name": user.full_name,
        "status": user.status,
        "employment_type": user.employment_type,
        "employee_code": user.employee_code,
    }


class UserService:
    def __init__(
        self,
        users: UserRepository,
        tokens: TokenRepository,
        rbac: RbacRepository,
        audit: AuditService,
        clock: Clock = utcnow,
        work: WorkRepository | None = None,
    ) -> None:
        self.users = users
        self.tokens = tokens
        self.rbac = rbac
        self.audit = audit
        self.clock = clock
        self.work = work

    async def create_user(self, actor: User, data: NewUser) -> tuple[User, ActivationLink]:
        email = data.email.strip().lower()
        if await self.users.get_by_email(email):
            raise ConflictError("Email is already used", code="email_taken")
        code = data.employee_code.strip() if data.employee_code else None
        if code and await self.users.get_by_employee_code(code):
            raise ConflictError("Employee code is already used", code="employee_code_taken")
        user = await self.users.add(
            User(
                id=uuid.uuid4(),
                email=email,
                full_name=data.full_name.strip(),
                employment_type=data.employment_type,
                employee_code=code,
                joined_at=data.joined_at,
                status=UserStatus.ACTIVE,
                token_version=0,
            )
        )
        link = await self._new_activation_link(user)
        await self.audit.record(
            actor=actor,
            action="user.create",
            target_type="user",
            target_id=user.id,
            after=user_snapshot(user),
        )
        return user, link

    async def reissue_activation(self, actor: User, user_id: uuid.UUID) -> ActivationLink:
        user = await self.get_user(user_id)
        if user.status != UserStatus.ACTIVE:
            raise InvalidStateError("User is not active", code="account_inactive")
        if user.is_activated:
            raise InvalidStateError("User is already activated", code="already_activated")
        link = await self._new_activation_link(user)
        await self.audit.record(
            actor=actor, action="user.activation_reissue", target_type="user", target_id=user.id
        )
        return link

    async def get_user(self, user_id: uuid.UUID) -> User:
        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found")
        return user

    async def get_user_with_roles(self, user_id: uuid.UUID) -> tuple[User, Assignments]:
        user = await self.get_user(user_id)
        return user, await self.rbac.active_platform_assignments(user.id, self.clock())

    async def list_users(
        self,
        *,
        q: str | None,
        status: str | None,
        employment_type: str | None,
        role: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[tuple[User, Assignments]], int]:
        now = self.clock()
        users, total = await self.users.search(
            q=q,
            status=status,
            employment_type=employment_type,
            role_code=role,
            now=now,
            offset=offset,
            limit=limit,
        )
        roles = await self.rbac.active_assignments_for_users([u.id for u in users], now)
        return [(u, roles[u.id]) for u in users], total

    async def disable_user(self, actor: User, user_id: uuid.UUID, status: str, reason: str) -> User:
        """Offboarding: the user loses every permission and session immediately."""
        if status not in (UserStatus.SUSPENDED, UserStatus.LEFT):
            raise InvalidStateError("Status must be suspended or left", code="invalid_status")
        if actor.id == user_id:
            raise ForbiddenError("You cannot disable yourself", code="self_disable_forbidden")
        user = await self.get_user(user_id)
        if user.status != UserStatus.ACTIVE:
            raise InvalidStateError("User is already disabled", code="already_disabled")

        now = self.clock()
        assignments = await self.rbac.active_platform_assignments(user.id, now)
        await self._ensure_not_last_hr_admin(assignments, now)

        before = user_snapshot(user)
        for assignment, _ in assignments:
            assignment.revoked_at = now
            assignment.revoked_by = actor.id
            assignment.revoke_reason = reason
        user.status = status
        if status == UserStatus.LEFT:
            user.left_at = now.date()
        user.token_version += 1
        await self.tokens.revoke_user_refresh_tokens(user.id, now)
        await self.tokens.close_open_action_tokens(user.id, ActionTokenPurpose.ACTIVATE, now)
        if self.work is not None:
            await self.users.end_memberships(user.id, now, reason)
            await self.work.release_jobs(now, user_id=user.id)
        await self.audit.record(
            actor=actor,
            action="user.disable",
            target_type="user",
            target_id=user.id,
            before={**before, "roles": [role.code for _, role in assignments]},
            after=user_snapshot(user),
            reason=reason,
        )
        return user

    async def _ensure_not_last_hr_admin(self, assignments: Assignments, now: datetime) -> None:
        for _, role in assignments:
            is_hr_admin = role.scope == RoleScope.PLATFORM and role.code == PlatformRole.HR_ADMIN
            if is_hr_admin and await self.rbac.count_active_holders(role.id, now) <= 1:
                raise ConflictError("This is the last active hr_admin", code="last_hr_admin")

    async def _new_activation_link(self, user: User) -> ActivationLink:
        now = self.clock()
        await self.tokens.close_open_action_tokens(user.id, ActionTokenPurpose.ACTIVATE, now)
        raw = new_opaque_token()
        expires_at = now + timedelta(hours=settings.ACTIVATION_TOKEN_HOURS)
        await self.tokens.add_action_token(
            UserActionToken(
                id=uuid.uuid4(),
                user_id=user.id,
                purpose=ActionTokenPurpose.ACTIVATE,
                token_hash=hash_opaque_token(raw),
                expires_at=expires_at,
            )
        )
        url = f"{settings.FRONTEND_URL.rstrip('/')}/activate?token={raw}"
        return ActivationLink(url=url, expires_at=expires_at)
