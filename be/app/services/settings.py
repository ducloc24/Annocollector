from typing import Any

from app.core.clock import Clock, utcnow
from app.core.exceptions import AppError
from app.domain import settings_catalog
from app.models.ops import SystemSetting
from app.models.user import User
from app.repositories.ops import OpsRepository
from app.services.audit import AuditService


class SettingsService:
    def __init__(self, ops: OpsRepository, audit: AuditService, clock: Clock = utcnow) -> None:
        self.ops = ops
        self.audit = audit
        self.clock = clock

    async def all(self) -> dict[str, Any]:
        return {**settings_catalog.defaults(), **await self.ops.settings()}

    async def get(self, key: str) -> int:
        return int((await self.all())[key])

    async def describe(self) -> list[dict[str, Any]]:
        values = await self.all()
        return [
            {
                "key": key,
                "label": spec["label"],
                "value": values[key],
                "default": spec["default"],
                "min": spec["min"],
                "max": spec["max"],
            }
            for key, spec in settings_catalog.SETTINGS.items()
        ]

    async def update(self, actor: User, changes: dict[str, Any]) -> dict[str, Any]:
        problems = [p for k, v in changes.items() if (p := settings_catalog.validate(k, v))]
        if problems:
            raise AppError(
                "Invalid settings", code="invalid_settings", details={"errors": problems}
            )
        before = await self.all()
        for key, value in changes.items():
            row = await self.ops.get_setting(key)
            if row is None:
                await self.ops.add(SystemSetting(key=key, value=value, updated_by=actor.id))
            else:
                row.value = value
                row.updated_by = actor.id
        await self.audit.record(
            actor=actor,
            action="system.settings_update",
            target_type="system_settings",
            target_id=None,
            before={k: before[k] for k in changes},
            after=changes,
        )
        return await self.all()
