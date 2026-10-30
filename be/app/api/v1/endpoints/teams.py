import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from app.api.deps import (
    AuthorizationDep,
    CurrentUser,
    ProjectRepositoryDep,
    TeamServiceDep,
    require_permission,
)
from app.core.clock import utcnow
from app.core.exceptions import ForbiddenError
from app.core.rbac_catalog import Perm
from app.models.project import Team, TeamMember
from app.models.user import User
from app.repositories.project import ProjectRepository
from app.schemas.project import (
    ReasonRequest,
    TeamCreate,
    TeamDetail,
    TeamMemberCreate,
    TeamMemberRead,
    TeamMemberUpdate,
    TeamRead,
    TeamUpdate,
)
from app.schemas.user import UserSummary

router = APIRouter(prefix="/teams", tags=["teams"])

TeamManager = Annotated[User, require_permission(Perm.TEAM_MANAGE)]


def _summary(team: Team, members: list[tuple[TeamMember, User]]) -> TeamRead:
    mine = [(m, u) for m, u in members if m.team_id == team.id]
    lead = next((u for m, u in mine if m.is_lead), None)
    return TeamRead(
        id=team.id,
        code=team.code,
        name=team.name,
        description=team.description,
        status=team.status,
        annotators=sum(1 for m, _ in mine if m.team_role == "annotator"),
        reviewers=sum(1 for m, _ in mine if m.team_role == "reviewer"),
        lead=UserSummary.model_validate(lead) if lead else None,
    )


async def _can_read(user: User, authz, perm_needed: bool = True) -> set[str]:
    perms = await authz.platform_permissions(user.id)
    if Perm.TEAM_MANAGE not in perms and Perm.TEAM_READ not in perms:
        raise ForbiddenError("Missing permission team.read", details={"permission": Perm.TEAM_READ})
    return set(perms)


async def _detail(repo: ProjectRepository, team: Team, show_members: bool) -> TeamDetail:
    members = await repo.team_members([team.id], utcnow())
    return TeamDetail(
        **_summary(team, members).model_dump(),
        members=[
            TeamMemberRead(
                id=m.id,
                user=UserSummary.model_validate(u),
                team_role=m.team_role,
                is_lead=m.is_lead,
                added_at=m.added_at,
                expires_at=m.expires_at,
            )
            for m, u in members
        ]
        if show_members
        else [],
    )


@router.post("", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
async def create_team(payload: TeamCreate, actor: TeamManager, teams: TeamServiceDep) -> TeamRead:
    team = await teams.create(actor, payload.code, payload.name, payload.description)
    return _summary(team, [])


@router.get("", response_model=list[TeamRead])
async def list_teams(
    user: CurrentUser,
    authz: AuthorizationDep,
    repo: ProjectRepositoryDep,
    q: str | None = Query(None, max_length=120),
    status_filter: Annotated[Literal["active", "archived"] | None, Query(alias="status")] = None,
) -> list[TeamRead]:
    await _can_read(user, authz)
    teams = await repo.list_teams(q, status_filter)
    members = await repo.team_members([t.id for t in teams], utcnow())
    return [_summary(t, members) for t in teams]


@router.get("/{team_id}", response_model=TeamDetail)
async def get_team(
    team_id: uuid.UUID,
    user: CurrentUser,
    authz: AuthorizationDep,
    teams: TeamServiceDep,
    repo: ProjectRepositoryDep,
) -> TeamDetail:
    perms = await _can_read(user, authz)
    team = await teams.get(team_id)
    return await _detail(repo, team, Perm.TEAM_MANAGE in perms or Perm.TEAM_READ in perms)


@router.patch("/{team_id}", response_model=TeamRead)
async def update_team(
    team_id: uuid.UUID,
    payload: TeamUpdate,
    actor: TeamManager,
    teams: TeamServiceDep,
    repo: ProjectRepositoryDep,
) -> TeamRead:
    team = await teams.update(actor, team_id, payload.model_dump(exclude_unset=True))
    return _summary(team, await repo.team_members([team.id], utcnow()))


@router.post("/{team_id}/members", response_model=TeamDetail, status_code=status.HTTP_201_CREATED)
async def add_team_member(
    team_id: uuid.UUID,
    payload: TeamMemberCreate,
    actor: TeamManager,
    teams: TeamServiceDep,
    repo: ProjectRepositoryDep,
) -> TeamDetail:
    await teams.add_member(actor, team_id, payload.user_id, payload.team_role, payload.expires_at)
    return await _detail(repo, await teams.get(team_id), True)


@router.patch("/{team_id}/members/{member_id}", response_model=TeamDetail)
async def update_team_member(
    team_id: uuid.UUID,
    member_id: uuid.UUID,
    payload: TeamMemberUpdate,
    actor: TeamManager,
    teams: TeamServiceDep,
    repo: ProjectRepositoryDep,
) -> TeamDetail:
    await teams.update_member(actor, team_id, member_id, payload.model_dump(exclude_unset=True))
    return await _detail(repo, await teams.get(team_id), True)


@router.delete("/{team_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member(
    team_id: uuid.UUID,
    member_id: uuid.UUID,
    payload: ReasonRequest,
    actor: TeamManager,
    teams: TeamServiceDep,
) -> Response:
    await teams.remove_member(actor, team_id, member_id, payload.reason)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
