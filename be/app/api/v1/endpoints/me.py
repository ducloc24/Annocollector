from typing import Any

from fastapi import APIRouter

from app.api.deps import (
    AuthorizationDep,
    CurrentUser,
    ProjectRepositoryDep,
    RbacRepositoryDep,
    WorkRepositoryDep,
)
from app.core.clock import utcnow
from app.models.project import ProjectStatus
from app.models.work import JobStatus
from app.repositories.work import OPEN_ANNOTATOR_STATUSES
from app.schemas.project import MyTeam
from app.schemas.user import MeRead, MyPermissions
from app.schemas.work import JobRead

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=MeRead, summary="Current user and platform roles")
async def me(user: CurrentUser, rbac: RbacRepositoryDep) -> MeRead:
    assignments = await rbac.active_platform_assignments(user.id, utcnow())
    return MeRead.build(user, assignments)


@router.get("/permissions", response_model=MyPermissions, summary="Effective platform permissions")
async def my_permissions(user: CurrentUser, authz: AuthorizationDep) -> MyPermissions:
    granted = await authz.platform_permissions(user.id)
    return MyPermissions(permissions={code: sorted(limits) for code, limits in granted.items()})


@router.get("/teams", response_model=list[MyTeam], summary="Teams I belong to")
async def my_teams(user: CurrentUser, repo: ProjectRepositoryDep) -> list[MyTeam]:
    return [
        MyTeam(team_id=t.id, code=t.code, name=t.name, team_role=m.team_role, is_lead=m.is_lead)
        for m, t in await repo.user_team_memberships(user.id, utcnow())
    ]


@router.get("/queues", summary="What I can work on, per project")
async def my_queues(
    user: CurrentUser, repo: ProjectRepositoryDep, work: WorkRepositoryDep, authz: AuthorizationDep
) -> list[dict[str, Any]]:
    """For each active project where I annotate or review: my open jobs and the queue size."""
    now = utcnow()
    result = []
    for project in await repo.list_projects(await repo.project_ids_for_user(user.id, now)):
        roles = await authz.project_roles(user.id, project.id)
        if not roles & {"annotator", "reviewer"}:
            continue
        team_rows = [
            r for r in await repo.team_roles_in_project(project.id, now) if r[0] == user.id
        ]
        reviewer_teams = [t for _, role, t in team_rows if role == "reviewer"]
        entry: dict[str, Any] = {
            "project": {
                "id": str(project.id),
                "code": project.code,
                "name": project.name,
                "status": project.status,
            },
            "roles": sorted(roles & {"annotator", "reviewer"}),
            "active": project.status == ProjectStatus.ACTIVE,
            "my_jobs": [],
            "my_reviews": [],
            "waiting_for_review": 0,
        }
        if "annotator" in roles:
            entry["my_jobs"] = [
                JobRead.model_validate(j).model_dump(mode="json")
                for j in await work.jobs_for_user(user.id, OPEN_ANNOTATOR_STATUSES)
                if j.project_id == project.id
            ]
        if "reviewer" in roles:
            entry["my_reviews"] = [
                JobRead.model_validate(j).model_dump(mode="json")
                for j in await work.jobs_in_review_by(user.id)
                if j.project_id == project.id and j.status == JobStatus.IN_REVIEW
            ]
            entry["waiting_for_review"] = await work.submitted_count(project.id, reviewer_teams)
        result.append(entry)
    return result
