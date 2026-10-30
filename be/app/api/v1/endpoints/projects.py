import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status
from fastapi.responses import PlainTextResponse

from app.api.deps import (
    AuthorizationDep,
    CurrentUser,
    ProjectAccess,
    ProjectRepositoryDep,
    ProjectServiceDep,
    require_permission,
    require_project_permission,
)
from app.core.clock import utcnow
from app.core.rbac_catalog import Perm
from app.models.user import User
from app.schemas.project import (
    GuidelineCreate,
    GuidelineRead,
    GuidelineSummary,
    MemberCreate,
    MemberRead,
    ProjectCreate,
    ProjectRead,
    ProjectTeamCreate,
    ProjectTeamLinked,
    ProjectTeamRead,
    ProjectUpdate,
    ProjectWithAccess,
    ReasonCodeCreate,
    ReasonCodeRead,
    ReasonCodeUpdate,
)
from app.schemas.user import UserSummary

router = APIRouter(prefix="/projects", tags=["projects"])

Member = Annotated[ProjectAccess, require_project_permission(None)]
Updater = Annotated[ProjectAccess, require_project_permission(Perm.PROJECT_UPDATE)]
MemberManager = Annotated[ProjectAccess, require_project_permission(Perm.MEMBER_MANAGE)]
GuidelineManager = Annotated[ProjectAccess, require_project_permission(Perm.GUIDELINE_MANAGE)]


async def _with_access(project, user_id, authz) -> ProjectWithAccess:
    roles = await authz.project_roles(user_id, project.id)
    perms = await authz.project_permissions(user_id, project.id)
    return ProjectWithAccess(
        **ProjectRead.model_validate(project).model_dump(),
        my_roles=sorted(roles),
        my_permissions=sorted(perms),
    )


@router.post("", response_model=ProjectWithAccess, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    actor: Annotated[User, require_permission(Perm.PROJECT_CREATE)],
    projects: ProjectServiceDep,
    authz: AuthorizationDep,
) -> ProjectWithAccess:
    project = await projects.create(
        actor,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        classification=payload.data_classification,
    )
    return await _with_access(project, actor.id, authz)


@router.get("", response_model=list[ProjectWithAccess], summary="Projects I belong to")
async def list_projects(
    user: CurrentUser, repo: ProjectRepositoryDep, authz: AuthorizationDep
) -> list[ProjectWithAccess]:
    ids = await repo.project_ids_for_user(user.id, utcnow())
    result = []
    for project in await repo.list_projects(ids):
        if await authz.project_roles(user.id, project.id):
            result.append(await _with_access(project, user.id, authz))
    return result


@router.get("/{project_id}", response_model=ProjectWithAccess)
async def get_project(
    access: Member, projects: ProjectServiceDep, authz: AuthorizationDep
) -> ProjectWithAccess:
    return await _with_access(await projects.get(access.project_id), access.user.id, authz)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    payload: ProjectUpdate, access: Updater, projects: ProjectServiceDep
) -> ProjectRead:
    project = await projects.update(
        access.user, access.project_id, payload.model_dump(exclude_unset=True)
    )
    return ProjectRead.model_validate(project)


@router.post("/{project_id}/activate", response_model=ProjectRead)
async def activate_project(access: Updater, projects: ProjectServiceDep) -> ProjectRead:
    return ProjectRead.model_validate(
        await projects.change_status(access.user, access.project_id, "activate")
    )


@router.post("/{project_id}/pause", response_model=ProjectRead)
async def pause_project(access: Updater, projects: ProjectServiceDep) -> ProjectRead:
    return ProjectRead.model_validate(
        await projects.change_status(access.user, access.project_id, "pause")
    )


@router.post("/{project_id}/close", response_model=ProjectRead)
async def close_project(access: Updater, projects: ProjectServiceDep) -> ProjectRead:
    return ProjectRead.model_validate(
        await projects.change_status(access.user, access.project_id, "close")
    )


# ---------- members ----------


@router.get("/{project_id}/members", response_model=list[MemberRead])
async def list_members(access: Member, repo: ProjectRepositoryDep) -> list[MemberRead]:
    return [
        MemberRead(
            id=m.id,
            user=UserSummary.model_validate(u),
            role=r.code,
            assigned_at=m.assigned_at,
            expires_at=m.expires_at,
        )
        for m, r, u in await repo.members(access.project_id, utcnow())
    ]


@router.post(
    "/{project_id}/members", response_model=MemberRead, status_code=status.HTTP_201_CREATED
)
async def add_member(
    payload: MemberCreate,
    access: MemberManager,
    projects: ProjectServiceDep,
    repo: ProjectRepositoryDep,
) -> MemberRead:
    member = await projects.add_member(
        access.user,
        access.project_id,
        payload.user_id,
        payload.role,
        payload.expires_at,
        set(access.roles),
    )
    user = await projects.users.get(member.user_id)
    return MemberRead(
        id=member.id,
        user=UserSummary.model_validate(user),
        role=payload.role,
        assigned_at=member.assigned_at,
        expires_at=member.expires_at,
    )


@router.delete("/{project_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    member_id: uuid.UUID, access: MemberManager, projects: ProjectServiceDep
) -> Response:
    await projects.remove_member(access.user, access.project_id, member_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{project_id}/candidates",
    response_model=list[UserSummary],
    summary="Active users holding the platform role a direct project role needs",
)
async def candidates(
    access: MemberManager,
    projects: ProjectServiceDep,
    role: Literal["owner", "manager", "viewer"] = "manager",
) -> list[UserSummary]:
    from app.core.rbac_catalog import ROLE_REQUIREMENTS, ProjectRole

    required = ROLE_REQUIREMENTS.get(ProjectRole(role))
    rows, _ = await projects.users.search(
        q=None,
        status="active",
        employment_type=None,
        role_code=required,
        now=utcnow(),
        offset=0,
        limit=100,
    )
    return [UserSummary.model_validate(u) for u in rows]


# ---------- teams on the project ----------


@router.get("/{project_id}/teams", response_model=list[ProjectTeamRead])
async def list_project_teams(access: Member, projects: ProjectServiceDep) -> list[ProjectTeamRead]:
    return [
        ProjectTeamRead(
            id=link.id,
            team_id=team.id,
            code=team.code,
            name=team.name,
            annotators=a,
            reviewers=r,
            assigned_at=link.assigned_at,
        )
        for link, team, a, r in await projects.teams_with_counts(access.project_id)
    ]


@router.post(
    "/{project_id}/teams", response_model=ProjectTeamLinked, status_code=status.HTTP_201_CREATED
)
async def link_team(
    payload: ProjectTeamCreate, access: MemberManager, projects: ProjectServiceDep
) -> ProjectTeamLinked:
    link, warnings = await projects.link_team(access.user, access.project_id, payload.team_id)
    row = next(r for r in await projects.teams_with_counts(access.project_id) if r[0].id == link.id)
    _, team, a, r = row
    return ProjectTeamLinked(
        link=ProjectTeamRead(
            id=link.id,
            team_id=team.id,
            code=team.code,
            name=team.name,
            annotators=a,
            reviewers=r,
            assigned_at=link.assigned_at,
        ),
        warnings=warnings,
    )


@router.delete("/{project_id}/teams/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_team(
    link_id: uuid.UUID, access: MemberManager, projects: ProjectServiceDep
) -> Response:
    await projects.unlink_team(access.user, access.project_id, link_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- guidelines ----------


@router.get("/{project_id}/guidelines", response_model=list[GuidelineSummary])
async def list_guidelines(access: Member, repo: ProjectRepositoryDep) -> list[GuidelineSummary]:
    return [GuidelineSummary.model_validate(g) for g in await repo.guidelines(access.project_id)]


@router.post(
    "/{project_id}/guidelines", response_model=GuidelineRead, status_code=status.HTTP_201_CREATED
)
async def add_guideline(
    payload: GuidelineCreate, access: GuidelineManager, projects: ProjectServiceDep
) -> GuidelineRead:
    return GuidelineRead.model_validate(
        await projects.add_guideline(access.user, access.project_id, payload.content)
    )


@router.get("/{project_id}/guidelines/{version}", response_model=GuidelineRead)
async def get_guideline(version: int, access: Member, projects: ProjectServiceDep) -> GuidelineRead:
    return GuidelineRead.model_validate(await projects.guideline(access.project_id, version))


@router.get("/{project_id}/guidelines/{version}/diff", response_class=PlainTextResponse)
async def guideline_diff(
    version: int, access: Member, projects: ProjectServiceDep, base: int = Query(alias="from", ge=1)
) -> str:
    return await projects.guideline_diff(access.project_id, version, base)


# ---------- reason codes ----------


@router.get("/{project_id}/reason-codes", response_model=list[ReasonCodeRead])
async def list_reason_codes(access: Member, repo: ProjectRepositoryDep) -> list[ReasonCodeRead]:
    return [ReasonCodeRead.model_validate(rc) for rc in await repo.reason_codes(access.project_id)]


@router.post(
    "/{project_id}/reason-codes", response_model=ReasonCodeRead, status_code=status.HTTP_201_CREATED
)
async def add_reason_code(
    payload: ReasonCodeCreate, access: Updater, projects: ProjectServiceDep
) -> ReasonCodeRead:
    rc = await projects.add_reason_code(
        access.user,
        access.project_id,
        payload.code,
        payload.label,
        payload.default_severity,
        payload.applies_to,
    )
    return ReasonCodeRead.model_validate(rc)


@router.patch("/{project_id}/reason-codes/{code_id}", response_model=ReasonCodeRead)
async def update_reason_code(
    code_id: uuid.UUID, payload: ReasonCodeUpdate, access: Updater, projects: ProjectServiceDep
) -> ReasonCodeRead:
    rc = await projects.update_reason_code(
        access.user, access.project_id, code_id, payload.model_dump(exclude_unset=True)
    )
    return ReasonCodeRead.model_validate(rc)
