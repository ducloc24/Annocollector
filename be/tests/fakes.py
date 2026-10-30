"""In-memory stand-ins for the repositories, so services are tested without a database."""

import uuid
from datetime import datetime
from typing import Any

from app.core import rbac_catalog as catalog
from app.models.audit import AuditEvent
from app.models.rbac import Role, UserPlatformRole
from app.models.user import RefreshToken, User, UserActionToken, UserStatus


def make_user(**overrides: Any) -> User:
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "email": f"{uuid.uuid4().hex[:8]}@company.vn",
        "full_name": "Test User",
        "employment_type": "full_time",
        "status": UserStatus.ACTIVE,
        "token_version": 0,
        "kind": "human",
    }
    values.update(overrides)
    return User(**values)


def _active(assignment: UserPlatformRole, now: datetime) -> bool:
    return assignment.revoked_at is None and (
        assignment.expires_at is None or assignment.expires_at > now
    )


class FakeUsers:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, User] = {}

    def put(self, user: User) -> User:
        self.by_id[user.id] = user
        return user

    async def get(self, user_id: uuid.UUID) -> User | None:
        return self.by_id.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        return next((u for u in self.by_id.values() if u.email == email), None)

    async def get_by_employee_code(self, code: str) -> User | None:
        return next((u for u in self.by_id.values() if u.employee_code == code), None)

    async def add(self, user: User) -> User:
        return self.put(user)


class FakeTokens:
    def __init__(self) -> None:
        self.refresh: list[RefreshToken] = []
        self.actions: list[UserActionToken] = []

    async def add_refresh(self, token: RefreshToken) -> RefreshToken:
        self.refresh.append(token)
        return token

    async def get_refresh_by_hash(self, token_hash: str) -> RefreshToken | None:
        return next((t for t in self.refresh if t.token_hash == token_hash), None)

    async def revoke_family(self, family_id: uuid.UUID, now: datetime) -> None:
        for t in self.refresh:
            if t.family_id == family_id and t.revoked_at is None:
                t.revoked_at = now

    async def revoke_user_refresh_tokens(
        self, user_id: uuid.UUID, now: datetime, *, keep_family: uuid.UUID | None = None
    ) -> None:
        for t in self.refresh:
            if t.user_id == user_id and t.revoked_at is None and t.family_id != keep_family:
                t.revoked_at = now

    async def add_action_token(self, token: UserActionToken) -> UserActionToken:
        self.actions.append(token)
        return token

    async def get_action_by_hash(self, token_hash: str) -> UserActionToken | None:
        return next((t for t in self.actions if t.token_hash == token_hash), None)

    async def close_open_action_tokens(
        self, user_id: uuid.UUID, purpose: str, now: datetime
    ) -> None:
        for t in self.actions:
            if t.user_id == user_id and t.purpose == purpose and t.used_at is None:
                t.used_at = now


class FakeRbac:
    """Role catalog straight from rbac_catalog plus in-memory assignments."""

    def __init__(self, users: FakeUsers) -> None:
        self.users = users
        self.roles = {
            (str(r.scope), str(r.code)): Role(
                id=r.id, code=str(r.code), scope=str(r.scope), name=r.name
            )
            for r in catalog.ROLES
        }
        self.assignments: list[UserPlatformRole] = []

    def role(self, code: str, scope: str = "platform") -> Role:
        return self.roles[(scope, code)]

    def give(self, user: User, code: str, **overrides: Any) -> UserPlatformRole:
        assignment = UserPlatformRole(
            id=uuid.uuid4(),
            user_id=user.id,
            role_id=self.role(code).id,
            granted_at=overrides.pop("granted_at", datetime(2026, 1, 1)),
            **overrides,
        )
        self.assignments.append(assignment)
        return assignment

    def _role_by_id(self, role_id: uuid.UUID) -> Role:
        return next(r for r in self.roles.values() if r.id == role_id)

    async def get_role(self, scope: str, code: str) -> Role | None:
        return self.roles.get((scope, code))

    async def active_platform_assignments(
        self, user_id: uuid.UUID, now: datetime
    ) -> list[tuple[UserPlatformRole, Role]]:
        return [
            (a, self._role_by_id(a.role_id))
            for a in self.assignments
            if a.user_id == user_id and _active(a, now)
        ]

    async def active_assignments_for_users(
        self, user_ids: list[uuid.UUID], now: datetime
    ) -> dict[uuid.UUID, list[tuple[UserPlatformRole, Role]]]:
        return {i: await self.active_platform_assignments(i, now) for i in user_ids}

    async def platform_grants(self, user_id: uuid.UUID, now: datetime) -> list[tuple[str, str]]:
        grants = []
        for _, role in await self.active_platform_assignments(user_id, now):
            for perm, limit in catalog.ROLE_PERMISSIONS[
                (catalog.RoleScope(role.scope), role.code)
            ].items():
                grants.append((str(perm), str(limit)))
        return grants

    async def add_assignment(self, assignment: UserPlatformRole) -> UserPlatformRole:
        self.assignments.append(assignment)
        return assignment

    async def count_active_holders(self, role_id: uuid.UUID, now: datetime) -> int:
        holders = {
            a.user_id
            for a in self.assignments
            if a.role_id == role_id
            and _active(a, now)
            and self.users.by_id[a.user_id].status == UserStatus.ACTIVE
        }
        return len(holders)


class FakeAuditRepo:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def add(self, event: AuditEvent) -> AuditEvent:
        self.events.append(event)
        return event

    def actions(self) -> list[str]:
        return [e.action for e in self.events]
