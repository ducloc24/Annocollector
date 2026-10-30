from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item


class ItemRepository:
    """Data-access layer: only talks to the database."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, item_id: int) -> Item | None:
        return await self.session.get(Item, item_id)

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[Item], int]:
        filters = []
        if search:
            filters.append(Item.name.ilike(f"%{search}%"))
        if is_active is not None:
            filters.append(Item.is_active.is_(is_active))

        total = await self.session.scalar(select(func.count()).select_from(Item).where(*filters))

        result = await self.session.scalars(
            select(Item).where(*filters).order_by(Item.id.desc()).offset(offset).limit(limit)
        )
        return list(result.all()), total or 0

    async def create(self, data: dict[str, Any]) -> Item:
        item = Item(**data)
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def update(self, item: Item, data: dict[str, Any]) -> Item:
        for field, value in data.items():
            setattr(item, field, value)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def delete(self, item: Item) -> None:
        await self.session.delete(item)
        await self.session.flush()
