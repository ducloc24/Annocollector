from pydantic import BaseModel


class RoleRead(BaseModel):
    code: str
    scope: str
    name: str
    description: str | None
    requires_platform_role: str | None = None


class PermissionGrant(BaseModel):
    role: str
    scope: str
    limit: str


class PermissionRead(BaseModel):
    code: str
    level: str
    description: str | None
    granted_to: list[PermissionGrant]
