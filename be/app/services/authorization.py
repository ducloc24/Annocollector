"""Permission resolver.

Checks run in the order of docs/database_design.md 3.6: the caller is already an active
user with a matching token_version (see AuthService.authenticate); here we resolve which
permissions their active roles grant and with which limit. Project roles join in at
build step 2.
"""

import uuid

from app.core.clock import Clock, utcnow
from app.core.exceptions import ForbiddenError
from app.core.rbac_catalog import Perm
from app.repositories.rbac import RbacRepository


class AuthorizationService:
    def __init__(self, rbac: RbacRepository, clock: Clock = utcnow) -> None:
        self.rbac = rbac
        self.clock = clock
        self._cache: dict[uuid.UUID, dict[str, set[str]]] = {}

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
