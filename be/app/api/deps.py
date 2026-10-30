from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

DbSession = Annotated[AsyncSession, Depends(get_db)]

MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class PageParams:
    offset: int
    limit: int


def get_page_params(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
) -> PageParams:
    return PageParams(offset=offset, limit=limit)


PageParamsDep = Annotated[PageParams, Depends(get_page_params)]
