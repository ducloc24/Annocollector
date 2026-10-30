"""Import every model here so Alembic autogenerate can see the metadata."""

from app.db.base import Base
from app.models.audit import AuditEvent
from app.models.rbac import (
    Permission,
    Role,
    RoleConflict,
    RolePermission,
    RoleRequirement,
    UserPlatformRole,
)
from app.models.user import RefreshToken, User, UserActionToken

__all__ = [
    "AuditEvent",
    "Base",
    "Permission",
    "RefreshToken",
    "Role",
    "RoleConflict",
    "RolePermission",
    "RoleRequirement",
    "User",
    "UserActionToken",
    "UserPlatformRole",
]
