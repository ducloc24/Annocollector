"""Import every model here so Alembic autogenerate can see the metadata."""

from app.db.base import Base
from app.models.item import Item

__all__ = ["Base", "Item"]
