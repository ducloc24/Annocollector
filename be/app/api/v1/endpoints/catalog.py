from typing import Annotated

from fastapi import APIRouter

from app.api.deps import CurrentUser, RbacRepositoryDep, require_permission
from app.core.rbac_catalog import Perm
from app.models.user import User
from app.schemas.rbac import PermissionGrant, PermissionRead, RoleRead

router = APIRouter(tags=["catalog"])


@router.get("/roles", response_model=list[RoleRead], summary="Role catalog")
async def list_roles(_: CurrentUser, rbac: RbacRepositoryDep) -> list[RoleRead]:
    roles = await rbac.list_roles()
    by_id = {r.id: r for r in roles}
    requires = {
        req.project_role_id: by_id[req.required_platform_role_id].code
        for req in await rbac.list_requirements()
    }
    return [
        RoleRead(
            code=r.code,
            scope=r.scope,
            name=r.name,
            description=r.description,
            requires_platform_role=requires.get(r.id),
        )
        for r in roles
    ]


@router.get("/permissions", response_model=list[PermissionRead], summary="Permission matrix")
async def list_permissions(
    _: Annotated[User, require_permission(Perm.AUDIT_READ)], rbac: RbacRepositoryDep
) -> list[PermissionRead]:
    grants: dict[str, list[PermissionGrant]] = {}
    for role, perm, limit in await rbac.list_permission_matrix():
        grants.setdefault(perm.code, []).append(
            PermissionGrant(role=role.code, scope=role.scope, limit=limit)
        )
    return [
        PermissionRead(
            code=p.code,
            level=p.level,
            description=p.description,
            granted_to=grants.get(p.code, []),
        )
        for p in await rbac.list_permissions()
    ]
