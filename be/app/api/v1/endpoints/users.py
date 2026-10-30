import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import (
    PageParamsDep,
    PlatformRoleServiceDep,
    UserServiceDep,
    require_permission,
)
from app.core.rbac_catalog import Perm
from app.models.user import User
from app.schemas.common import Page
from app.schemas.user import (
    ActivationLinkRead,
    DisableUserRequest,
    EmploymentType,
    ExpiringRoleRead,
    ExtendRoleRequest,
    GrantRoleRequest,
    RevokeRoleRequest,
    RoleAssignmentRead,
    UserCreate,
    UserCreated,
    UserRead,
    UserStatusValue,
    UserSummary,
)
from app.services.user import NewUser

router = APIRouter(tags=["users"])

UserManager = Annotated[User, require_permission(Perm.USER_MANAGE)]
RoleGranter = Annotated[User, require_permission(Perm.PLATFORM_ROLE_GRANT)]


@router.post(
    "/users",
    response_model=UserCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user and return a one-time activation link",
)
async def create_user(
    payload: UserCreate, actor: UserManager, users: UserServiceDep
) -> UserCreated:
    user, link = await users.create_user(
        actor,
        NewUser(
            email=payload.email,
            full_name=payload.full_name,
            employment_type=payload.employment_type,
            employee_code=payload.employee_code,
            joined_at=payload.joined_at,
        ),
    )
    return UserCreated(
        user=UserRead.build(user, []),
        activation_url=link.url,
        activation_expires_at=link.expires_at,
    )


@router.post(
    "/users/{user_id}/activation-link",
    response_model=ActivationLinkRead,
    summary="Issue a new activation link (the previous one stops working)",
)
async def reissue_activation(
    user_id: uuid.UUID, actor: UserManager, users: UserServiceDep
) -> ActivationLinkRead:
    link = await users.reissue_activation(actor, user_id)
    return ActivationLinkRead(activation_url=link.url, activation_expires_at=link.expires_at)


@router.get("/users", response_model=Page[UserRead], summary="Search users")
async def list_users(
    _: UserManager,
    users: UserServiceDep,
    page: PageParamsDep,
    q: str | None = Query(None, max_length=120),
    status_filter: Annotated[UserStatusValue | None, Query(alias="status")] = None,
    employment_type: EmploymentType | None = None,
    role: str | None = Query(None, max_length=64),
) -> Page[UserRead]:
    rows, total = await users.list_users(
        q=q,
        status=status_filter,
        employment_type=employment_type,
        role=role,
        offset=page.offset,
        limit=page.limit,
    )
    return Page[UserRead](
        items=[UserRead.build(u, a) for u, a in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/users/{user_id}", response_model=UserRead, summary="Get a user")
async def get_user(user_id: uuid.UUID, _: UserManager, users: UserServiceDep) -> UserRead:
    user, assignments = await users.get_user_with_roles(user_id)
    return UserRead.build(user, assignments)


@router.post(
    "/users/{user_id}/disable",
    response_model=UserRead,
    summary="Offboard a user: revoke every role and session immediately",
)
async def disable_user(
    user_id: uuid.UUID, payload: DisableUserRequest, actor: UserManager, users: UserServiceDep
) -> UserRead:
    user = await users.disable_user(actor, user_id, payload.status, payload.reason)
    return UserRead.build(user, [])


@router.post(
    "/users/{user_id}/platform-roles",
    response_model=RoleAssignmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Grant a platform role",
)
async def grant_role(
    user_id: uuid.UUID,
    payload: GrantRoleRequest,
    actor: RoleGranter,
    roles: PlatformRoleServiceDep,
) -> RoleAssignmentRead:
    assignment, role = await roles.grant(
        actor,
        user_id,
        payload.role,
        expires_at=payload.expires_at,
        acknowledge_warning=payload.acknowledge_warning,
    )
    return RoleAssignmentRead.build(assignment, role)


@router.patch(
    "/users/{user_id}/platform-roles/{assignment_id}",
    response_model=RoleAssignmentRead,
    summary="Change when a platform role expires",
)
async def extend_role(
    user_id: uuid.UUID,
    assignment_id: uuid.UUID,
    payload: ExtendRoleRequest,
    actor: RoleGranter,
    roles: PlatformRoleServiceDep,
) -> RoleAssignmentRead:
    assignment, role = await roles.extend(actor, user_id, assignment_id, payload.expires_at)
    return RoleAssignmentRead.build(assignment, role)


@router.delete(
    "/users/{user_id}/platform-roles/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a platform role",
)
async def revoke_role(
    user_id: uuid.UUID,
    assignment_id: uuid.UUID,
    payload: RevokeRoleRequest,
    actor: RoleGranter,
    roles: PlatformRoleServiceDep,
) -> Response:
    await roles.revoke(actor, user_id, assignment_id, payload.reason)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/platform-roles/expiring",
    response_model=list[ExpiringRoleRead],
    summary="Platform roles that expire soon",
)
async def expiring_roles(
    _: RoleGranter,
    roles: PlatformRoleServiceDep,
    within_days: int = Query(30, ge=1, le=365),
) -> list[ExpiringRoleRead]:
    rows = await roles.expiring(within_days)
    return [
        ExpiringRoleRead(
            **RoleAssignmentRead.build(a, r).model_dump(), user=UserSummary.model_validate(u)
        )
        for a, r, u in rows
    ]
