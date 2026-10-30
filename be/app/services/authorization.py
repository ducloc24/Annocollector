"""Permission resolver.

Checks run in the order of docs/database_design.md 3.6: the caller is already an active
user with a matching token_version (see AuthService.authenticate); here we resolve which
roles apply and which permissions (with limits) they grant.

Project roles come from two places: direct membership (owner, manager, viewer) and teams
linked to the project (annotator, reviewer). A project role only counts while the platform
role it requires is still active, so revoking a platform role takes effect immediately.
"""

import uuid

from app.core.clock import Clock, utcnow
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.rbac_catalog import ROLE_REQUIREMENTS, Perm, ProjectRole
from app.repositories.rbac import RbacRepository


class AuthorizationService:
    def __init__(self, rbac: RbacRepository, clock: Clock = utcnow) -> None:
        self.rbac = rbac
        self.clock = clock
        self._cache: dict[uuid.UUID, dict[str, set[str]]] = {}
        self._project_roles: dict[tuple[uuid.UUID, uuid.UUID], set[str]] = {}
        self._project_cache: dict[tuple[uuid.UUID, uuid.UUID], dict[str, set[str]]] = {}

    async def platform_permissions(self, user_id: uuid.UUID) -> dict[str, set[str]]:
        """Permission code -> limits granted by the user's active platform roles."""
        if user_id not in self._cache:
            granted: dict[str, set[str]] = {}
            for code, limit in await self.rbac.platform_grants(user_id, self.clock()):
                granted.setdefault(code, set()).add(limit)
            self._cache[user_id] = granted
        return self._cache[user_id]

    async def limits(self, user_id: uuid.UUID, perm: Perm) -> set[str]:
        return (await self.platform_permissions(user_id)).get(perm, set())

    async def require(self, user_id: uuid.UUID, perm: Perm) -> set[str]:
        """Return the limits for ``perm``; raise 403 when the user has none."""
        limits = await self.limits(user_id, perm)
        if not limits:
            raise ForbiddenError(f"Missing permission {perm}", details={"permission": perm})
        return limits

    async def project_roles(self, user_id: uuid.UUID, project_id: uuid.UUID) -> set[str]:
        key = (user_id, project_id)
        if key not in self._project_roles:
            now = self.clock()
            platform = await self.rbac.active_platform_role_codes(user_id, now)
            candidates = await self.rbac.direct_project_roles(user_id, project_id, now)
            candidates |= await self.rbac.team_project_roles(user_id, project_id, now)
            self._project_roles[key] = {
                role
                for role in candidates
                if (required := ROLE_REQUIREMENTS.get(ProjectRole(role))) is None
                or required in platform
            }
        return self._project_roles[key]

    async def project_permissions(
        self, user_id: uuid.UUID, project_id: uuid.UUID
    ) -> dict[str, set[str]]:
        key = (user_id, project_id)
        if key not in self._project_cache:
            granted: dict[str, set[str]] = {}
            roles = await self.project_roles(user_id, project_id)
            for code, limit in await self.rbac.project_role_grants(roles):
                granted.setdefault(code, set()).add(limit)
            self._project_cache[key] = granted
        return self._project_cache[key]

    async def require_member(self, user_id: uuid.UUID, project_id: uuid.UUID) -> set[str]:
        """Any project role. Outsiders get 404 so a project's existence is not revealed."""
        roles = await self.project_roles(user_id, project_id)
        if not roles:
            raise NotFoundError("Project not found")
        return roles

    async def require_project(
        self, user_id: uuid.UUID, project_id: uuid.UUID, perm: Perm
    ) -> set[str]:
        await self.require_member(user_id, project_id)
        limits = (await self.project_permissions(user_id, project_id)).get(perm, set())
        if not limits:
            raise ForbiddenError(f"Missing permission {perm}", details={"permission": perm})
        return limits
