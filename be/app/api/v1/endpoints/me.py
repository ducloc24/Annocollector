from fastapi import APIRouter

from app.api.deps import AuthorizationDep, CurrentUser, RbacRepositoryDep
from app.core.clock import utcnow
from app.schemas.user import MeRead, MyPermissions

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=MeRead, summary="Current user and platform roles")
async def me(user: CurrentUser, rbac: RbacRepositoryDep) -> MeRead:
    assignments = await rbac.active_platform_assignments(user.id, utcnow())
    return MeRead.build(user, assignments)


@router.get("/permissions", response_model=MyPermissions, summary="Effective platform permissions")
async def my_permissions(user: CurrentUser, authz: AuthorizationDep) -> MyPermissions:
    granted = await authz.platform_permissions(user.id)
    return MyPermissions(permissions={code: sorted(limits) for code, limits in granted.items()})
