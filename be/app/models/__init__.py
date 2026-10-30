"""Import every model here so Alembic autogenerate can see the metadata."""

from app.db.base import Base

__all__ = ["Base"]
