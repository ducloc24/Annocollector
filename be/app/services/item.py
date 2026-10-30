from app.core.exceptions import NotFoundError
from app.models.item import Item
from app.repositories.item import ItemRepository
from app.schemas.item import ItemCreate, ItemUpdate


class ItemService:
    """Business-logic layer: orchestrates repositories, raises domain errors."""

    def __init__(self, repository: ItemRepository) -> None:
        self.repository = repository

    async def list_items(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[Item], int]:
        return await self.repository.list(
            offset=offset, limit=limit, search=search, is_active=is_active
        )

    async def get_item(self, item_id: int) -> Item:
        item = await self.repository.get(item_id)
        if item is None:
            raise NotFoundError(f"Item {item_id} not found")
        return item

    async def create_item(self, payload: ItemCreate) -> Item:
        return await self.repository.create(payload.model_dump())

    async def update_item(self, item_id: int, payload: ItemUpdate) -> Item:
        item = await self.get_item(item_id)
        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            return item
        return await self.repository.update(item, changes)

    async def delete_item(self, item_id: int) -> None:
        item = await self.get_item(item_id)
        await self.repository.delete(item)
