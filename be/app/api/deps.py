import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.rbac_catalog import Perm
from app.core.storage import get_storage
from app.db.session import get_db
from app.models.user import User
from app.repositories.audit import AuditRepository
from app.repositories.ops import OpsRepository
from app.repositories.project import ProjectRepository
from app.repositories.rbac import RbacRepository
from app.repositories.user import TokenRepository, UserRepository
from app.repositories.work import WorkRepository
from app.services.appeal import AppealService
from app.services.audit import AuditService
from app.services.auth import AuthService
from app.services.authorization import AuthorizationService
from app.services.dataset import DatasetService
from app.services.platform_role import PlatformRoleService
from app.services.progress import ProgressService
from app.services.project import ProjectService
from app.services.quality import QualityService
from app.services.settings import SettingsService
from app.services.task import TaskService
from app.services.team import TeamService
from app.services.user import UserService
from app.services.work import WorkService

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
        UserRepository(session),
        TokenRepository(session),
        RbacRepository(session),
        audit,
        work=WorkRepository(session),
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


# ---------- project scope (build steps 2-7) ----------


def get_project_repository(session: DbSession) -> ProjectRepository:
    return ProjectRepository(session)


ProjectRepositoryDep = Annotated[ProjectRepository, Depends(get_project_repository)]


def get_work_repository(session: DbSession) -> WorkRepository:
    return WorkRepository(session)


WorkRepositoryDep = Annotated[WorkRepository, Depends(get_work_repository)]


def get_project_service(session: DbSession, audit: AuditServiceDep) -> ProjectService:
    return ProjectService(
        ProjectRepository(session),
        WorkRepository(session),
        UserRepository(session),
        RbacRepository(session),
        audit,
    )


ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]


def get_team_service(session: DbSession, audit: AuditServiceDep) -> TeamService:
    return TeamService(
        ProjectRepository(session),
        WorkRepository(session),
        UserRepository(session),
        RbacRepository(session),
        audit,
    )


TeamServiceDep = Annotated[TeamService, Depends(get_team_service)]


def get_settings_service(session: DbSession, audit: AuditServiceDep) -> SettingsService:
    return SettingsService(OpsRepository(session), audit)


SettingsServiceDep = Annotated[SettingsService, Depends(get_settings_service)]


def get_dataset_service(
    session: DbSession, audit: AuditServiceDep, app_settings: SettingsServiceDep
) -> DatasetService:
    return DatasetService(
        ProjectRepository(session),
        WorkRepository(session),
        get_storage(),
        audit,
        app_settings=app_settings,
    )


DatasetServiceDep = Annotated[DatasetService, Depends(get_dataset_service)]


def get_task_service(session: DbSession, audit: AuditServiceDep) -> TaskService:
    return TaskService(ProjectRepository(session), WorkRepository(session), audit)


TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]


def get_work_service(session: DbSession, audit: AuditServiceDep) -> WorkService:
    return WorkService(ProjectRepository(session), WorkRepository(session), audit)


WorkServiceDep = Annotated[WorkService, Depends(get_work_service)]


def get_progress_service(
    session: DbSession, audit: AuditServiceDep, app_settings: SettingsServiceDep
) -> ProgressService:
    return ProgressService(WorkRepository(session), audit, app_settings=app_settings)


ProgressServiceDep = Annotated[ProgressService, Depends(get_progress_service)]


def get_appeal_service(
    session: DbSession, audit: AuditServiceDep, app_settings: SettingsServiceDep
) -> AppealService:
    return AppealService(OpsRepository(session), WorkRepository(session), app_settings, audit)


AppealServiceDep = Annotated[AppealService, Depends(get_appeal_service)]


def get_quality_service(
    session: DbSession, audit: AuditServiceDep, app_settings: SettingsServiceDep
) -> QualityService:
    return QualityService(
        OpsRepository(session),
        ProjectRepository(session),
        WorkRepository(session),
        app_settings,
        audit,
    )


QualityServiceDep = Annotated[QualityService, Depends(get_quality_service)]


@dataclass(frozen=True)
class ProjectAccess:
    user: User
    project_id: uuid.UUID
    roles: frozenset[str]
    limits: frozenset[str]


def require_project_permission(perm: Perm | None) -> Any:
    """Dependency for routes with a ``project_id`` path parameter.

    ``None`` only requires some role in the project (outsiders get 404).
    """

    async def dependency(
        project_id: uuid.UUID, user: CurrentUser, authz: AuthorizationDep
    ) -> ProjectAccess:
        roles = await authz.require_member(user.id, project_id)
        limits = await authz.require_project(user.id, project_id, perm) if perm else set()
        return ProjectAccess(user, project_id, frozenset(roles), frozenset(limits))

    checker: Callable[..., Awaitable[ProjectAccess]] = dependency
    return Depends(checker)
