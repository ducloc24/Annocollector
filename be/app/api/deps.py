from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.rbac_catalog import Perm
from app.db.session import get_db
from app.models.user import User
from app.repositories.audit import AuditRepository
from app.repositories.rbac import RbacRepository
from app.repositories.user import TokenRepository, UserRepository
from app.services.audit import AuditService
from app.services.auth import AuthService
from app.services.authorization import AuthorizationService
from app.services.platform_role import PlatformRoleService
from app.services.user import UserService

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


def get_audit_service(session: DbSession) -> AuditService:
    return AuditService(AuditRepository(session))


AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]


def get_auth_service(session: DbSession, audit: AuditServiceDep) -> AuthService:
    return AuthService(UserRepository(session), TokenRepository(session), audit)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_authorization_service(session: DbSession) -> AuthorizationService:
    return AuthorizationService(RbacRepository(session))


AuthorizationDep = Annotated[AuthorizationService, Depends(get_authorization_service)]


def get_user_service(session: DbSession, audit: AuditServiceDep) -> UserService:
    return UserService(
        UserRepository(session), TokenRepository(session), RbacRepository(session), audit
    )


UserServiceDep = Annotated[UserService, Depends(get_user_service)]


def get_platform_role_service(session: DbSession, audit: AuditServiceDep) -> PlatformRoleService:
    return PlatformRoleService(UserRepository(session), RbacRepository(session), audit)


PlatformRoleServiceDep = Annotated[PlatformRoleService, Depends(get_platform_role_service)]


def get_rbac_repository(session: DbSession) -> RbacRepository:
    return RbacRepository(session)


RbacRepositoryDep = Annotated[RbacRepository, Depends(get_rbac_repository)]

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    auth: AuthServiceDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise UnauthorizedError("Missing access token")
    return await auth.authenticate(credentials.credentials)


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_permission(perm: Perm) -> Any:
    """Dependency that returns the current user after checking a platform permission."""

    async def dependency(user: CurrentUser, authz: AuthorizationDep) -> User:
        await authz.require(user.id, perm)
        return user

    checker: Callable[..., Awaitable[User]] = dependency
    return Depends(checker)
