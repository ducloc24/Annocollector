from fastapi import APIRouter, Query, Response, status

from app.api.deps import ItemServiceDep
from app.models.item import Item
from app.schemas.common import Page
from app.schemas.item import ItemCreate, ItemRead, ItemUpdate

router = APIRouter(prefix="/items", tags=["items"])


@router.get("", response_model=Page[ItemRead], summary="List items")
async def list_items(
    service: ItemServiceDep,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=120),
    is_active: bool | None = None,
) -> Page[ItemRead]:
    items, total = await service.list_items(
        offset=offset, limit=limit, search=search, is_active=is_active
    )
    return Page[ItemRead](items=items, total=total, limit=limit, offset=offset)


@router.post(
    "", response_model=ItemRead, status_code=status.HTTP_201_CREATED, summary="Create item"
)
async def create_item(payload: ItemCreate, service: ItemServiceDep) -> Item:
    return await service.create_item(payload)


@router.get("/{item_id}", response_model=ItemRead, summary="Get item")
async def get_item(item_id: int, service: ItemServiceDep) -> Item:
    return await service.get_item(item_id)


@router.patch("/{item_id}", response_model=ItemRead, summary="Update item")
async def update_item(item_id: int, payload: ItemUpdate, service: ItemServiceDep) -> Item:
    return await service.update_item(item_id, payload)


@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete item",
)
async def delete_item(item_id: int, service: ItemServiceDep) -> Response:
    await service.delete_item(item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
