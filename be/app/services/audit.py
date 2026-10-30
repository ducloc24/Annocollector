import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from app.core.request_context import get_request_context
from app.models.audit import AuditEvent
from app.models.user import User
from app.repositories.audit import AuditRepository

SYSTEM_ACTOR_NAME = "system"

# Target types hr_admin may read through audit.read with limit "rbac".
ACCESS_CONTROL_TARGETS = ("user", "platform_role")


class AuditService:
    def __init__(self, repo: AuditRepository) -> None:
        self.repo = repo

    async def record(
        self,
        *,
        actor: User | None,
        action: str,
        target_type: str,
        target_id: uuid.UUID | str | None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        reason: str | None = None,
        project_id: uuid.UUID | None = None,
    ) -> AuditEvent:
        """Append an audit event in the caller's transaction."""
        ctx = get_request_context()
        event = AuditEvent(
            actor_id=actor.id if actor else None,
            actor_name=actor.full_name if actor else SYSTEM_ACTOR_NAME,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            project_id=project_id,
            before=before,
            after=after,
            reason=reason,
            request_id=ctx.request_id if ctx else None,
            ip=ctx.ip if ctx else None,
            user_agent=ctx.user_agent if ctx else None,
        )
        return await self.repo.add(event)

    async def search(
        self,
        *,
        access_control_only: bool,
        actor_id: uuid.UUID | None = None,
        action: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        project_id: uuid.UUID | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        offset: int,
        limit: int,
    ) -> tuple[list[AuditEvent], int]:
        only: Sequence[str] | None = ACCESS_CONTROL_TARGETS if access_control_only else None
        return await self.repo.search(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            project_id=project_id,
            since=since,
            until=until,
            only_target_types=only,
            offset=offset,
            limit=limit,
        )
