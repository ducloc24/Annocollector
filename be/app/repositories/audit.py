import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, event: AuditEvent) -> AuditEvent:
        self.session.add(event)
        await self.session.flush()
        return event

    async def search(
        self,
        *,
        actor_id: uuid.UUID | None,
        action: str | None,
        target_type: str | None,
        target_id: str | None,
        project_id: uuid.UUID | None,
        since: datetime | None,
        until: datetime | None,
        only_target_types: Sequence[str] | None,
        offset: int,
        limit: int,
    ) -> tuple[list[AuditEvent], int]:
        stmt = select(AuditEvent)
        if actor_id:
            stmt = stmt.where(AuditEvent.actor_id == actor_id)
        if action:
            stmt = stmt.where(AuditEvent.action == action)
        if target_type:
            stmt = stmt.where(AuditEvent.target_type == target_type)
        if target_id:
            stmt = stmt.where(AuditEvent.target_id == target_id)
        if project_id:
            stmt = stmt.where(AuditEvent.project_id == project_id)
        if since:
            stmt = stmt.where(AuditEvent.created_at >= since)
        if until:
            stmt = stmt.where(AuditEvent.created_at < until)
        if only_target_types is not None:
            stmt = stmt.where(AuditEvent.target_type.in_(only_target_types))
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self.session.scalars(
            stmt.order_by(AuditEvent.created_at.desc(), AuditEvent.id).offset(offset).limit(limit)
        )
        return list(rows), total or 0
