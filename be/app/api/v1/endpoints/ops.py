"""Appeals, overrides, gold jobs, quality, export, team lead views, system settings."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.api.deps import (
    AppealServiceDep,
    AuditServiceDep,
    AuthorizationDep,
    CurrentUser,
    PageParamsDep,
    ProjectAccess,
    ProjectRepositoryDep,
    QualityServiceDep,
    SettingsServiceDep,
    TeamServiceDep,
    WorkRepositoryDep,
    require_permission,
    require_project_permission,
)
from app.core.exceptions import NotFoundError
from app.core.rbac_catalog import Perm
from app.domain.item_types import ITEM_TYPES
from app.domain.parsers import PARSERS
from app.models.ops import Appeal
from app.models.user import User
from app.schemas.audit import AuditEventRead
from app.schemas.common import Page
from app.schemas.work import JobRead

router = APIRouter(tags=["ops"])

Member = Annotated[ProjectAccess, require_project_permission(None)]
Overrider = Annotated[ProjectAccess, require_project_permission(Perm.REVIEW_OVERRIDE)]
Decider = Annotated[ProjectAccess, require_project_permission(Perm.APPEAL_DECIDE)]
Assigner = Annotated[ProjectAccess, require_project_permission(Perm.JOB_ASSIGN)]
QualityReader = Annotated[ProjectAccess, require_project_permission(Perm.QUALITY_READ)]
Exporter = Annotated[ProjectAccess, require_project_permission(Perm.EXPORT_DATA)]
Auditor = Annotated[ProjectAccess, require_project_permission(Perm.AUDIT_READ)]
Configurer = Annotated[User, require_permission(Perm.SYSTEM_CONFIGURE)]


class AppealRead(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    job_ordinal: int | None = None
    opened_by: uuid.UUID
    opener_name: str | None = None
    reason: str
    status: str
    outcome: str | None
    resolution: str | None
    opened_at: datetime
    resolved_at: datetime | None


class AppealOpen(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class AppealDecision(BaseModel):
    action: Literal["upheld", "overturned", "forward"]
    resolution: str = Field(min_length=3, max_length=2000)


class OverrideRequest(BaseModel):
    decision: Literal["accept", "reject"]
    reason: str = Field(min_length=3, max_length=2000)


class GoldRequest(BaseModel):
    job_id: uuid.UUID


class SettingsUpdate(BaseModel):
    values: dict[str, Any]


async def _appeal_read(appeal: Appeal, work: Any, users: Any) -> AppealRead:
    job = await work.get_job(appeal.job_id)
    opener = await users.session.get(User, appeal.opened_by)
    return AppealRead(
        id=appeal.id,
        job_id=appeal.job_id,
        job_ordinal=job.ordinal if job else None,
        opened_by=appeal.opened_by,
        opener_name=opener.full_name if opener else None,
        reason=appeal.reason,
        status=appeal.status,
        outcome=appeal.outcome,
        resolution=appeal.resolution,
        opened_at=appeal.opened_at,
        resolved_at=appeal.resolved_at,
    )


# ---------- appeals and overrides ----------


@router.post("/jobs/{job_id}/appeals", response_model=AppealRead, status_code=201)
async def open_appeal(
    job_id: uuid.UUID,
    payload: AppealOpen,
    user: CurrentUser,
    appeals: AppealServiceDep,
    authz: AuthorizationDep,
    work: WorkRepositoryDep,
    repo: ProjectRepositoryDep,
) -> AppealRead:
    job = await work.get_job(job_id)
    if job is None:
        raise NotFoundError("Job not found")
    await authz.require_project(user.id, job.project_id, Perm.APPEAL_OPEN)
    appeal = await appeals.open(user, job_id, payload.reason)
    return await _appeal_read(appeal, work, repo)


@router.get("/projects/{project_id}/appeals", response_model=list[AppealRead])
async def list_appeals(
    access: Decider,
    appeals: AppealServiceDep,
    work: WorkRepositoryDep,
    repo: ProjectRepositoryDep,
    status: str | None = None,
) -> list[AppealRead]:
    rows = await appeals.ops.appeals(access.project_id, status=status)
    return [await _appeal_read(a, work, repo) for a in rows]


@router.get("/me/appeals", response_model=list[AppealRead])
async def my_appeals(
    user: CurrentUser,
    appeals: AppealServiceDep,
    work: WorkRepositoryDep,
    repo: ProjectRepositoryDep,
) -> list[AppealRead]:
    rows = await appeals.ops.appeals_of_user(user.id)
    return [await _appeal_read(a, work, repo) for a in rows]


@router.post("/projects/{project_id}/appeals/{appeal_id}/decision", response_model=AppealRead)
async def decide_appeal(
    appeal_id: uuid.UUID,
    payload: AppealDecision,
    access: Decider,
    appeals: AppealServiceDep,
    work: WorkRepositoryDep,
    repo: ProjectRepositoryDep,
) -> AppealRead:
    existing = await appeals.ops.get_appeal(appeal_id)
    if existing is None or existing.project_id != access.project_id:
        raise NotFoundError("Appeal not found")
    appeal = await appeals.decide(
        access.user, set(access.roles), appeal_id, payload.action, payload.resolution
    )
    return await _appeal_read(appeal, work, repo)


@router.post("/projects/{project_id}/jobs/{job_id}/override", response_model=JobRead)
async def override_review(
    job_id: uuid.UUID, payload: OverrideRequest, access: Overrider, appeals: AppealServiceDep
) -> JobRead:
    job = await appeals.override(
        access.user, access.project_id, job_id, payload.decision, payload.reason
    )
    return JobRead.model_validate(job)


# ---------- gold jobs ----------


@router.post("/projects/{project_id}/gold-jobs", response_model=JobRead, status_code=201)
async def make_gold(payload: GoldRequest, access: Assigner, quality: QualityServiceDep) -> JobRead:
    return JobRead.model_validate(
        await quality.make_gold(access.user, access.project_id, payload.job_id)
    )


# ---------- quality ----------


@router.get("/projects/{project_id}/quality")
async def project_quality(access: QualityReader, quality: QualityServiceDep) -> dict[str, Any]:
    report = await quality.project_report(access.project_id)
    if "project" not in access.limits:
        # Annotators and reviewers only see their own line.
        mine = str(access.user.id)
        report["annotators"] = [a for a in report["annotators"] if a["user_id"] == mine]
        report["reviewers"] = [r for r in report["reviewers"] if r["user_id"] == mine]
    return report


@router.get("/me/quality")
async def my_quality(
    user: CurrentUser,
    quality: QualityServiceDep,
    repo: ProjectRepositoryDep,
    authz: AuthorizationDep,
) -> list[dict[str, Any]]:
    from app.core.clock import utcnow

    ids = []
    for pid in await repo.project_ids_for_user(user.id, utcnow()):
        if await authz.project_roles(user.id, pid) & {"annotator", "reviewer"}:
            ids.append(pid)
    return await quality.my_report(user, ids)


# ---------- export ----------


@router.get("/projects/{project_id}/tasks/{task_id}/export", response_class=PlainTextResponse)
async def export_task(task_id: uuid.UUID, access: Exporter, quality: QualityServiceDep) -> Response:
    text = await quality.export_task(access.user, access.project_id, task_id)
    return PlainTextResponse(
        text,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="task-{task_id}.jsonl"'},
    )


# ---------- project audit ----------


@router.get("/projects/{project_id}/audit-events", response_model=Page[AuditEventRead])
async def project_audit(
    access: Auditor,
    audit: AuditServiceDep,
    page: PageParamsDep,
    action: str | None = Query(None, max_length=64),
) -> Page[AuditEventRead]:
    events, total = await audit.search(
        access_control_only=False,
        project_id=access.project_id,
        action=action,
        offset=page.offset,
        limit=page.limit,
    )
    return Page[AuditEventRead](
        items=[AuditEventRead.model_validate(e) for e in events],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


# ---------- team lead ----------


@router.get("/teams/{team_id}/overview")
async def team_overview(
    team_id: uuid.UUID, user: CurrentUser, quality: QualityServiceDep
) -> list[dict[str, Any]]:
    return await quality.team_overview(user, team_id)


@router.get("/teams/{team_id}/quality")
async def team_quality(
    team_id: uuid.UUID, user: CurrentUser, quality: QualityServiceDep
) -> dict[str, Any]:
    return await quality.team_quality(user, team_id)


@router.get("/teams/{team_id}/alerts")
async def team_alerts(
    team_id: uuid.UUID, user: CurrentUser, quality: QualityServiceDep
) -> list[dict[str, str]]:
    return await quality.team_alerts(user, team_id)


_ = TeamServiceDep  # reserved for lead-managed actions


# ---------- system ----------


@router.get("/system/settings")
async def get_settings(_: Configurer, app_settings: SettingsServiceDep) -> dict[str, Any]:
    return {
        "settings": await app_settings.describe(),
        "parsers": [
            {
                "name": p.name,
                "version": p.version,
                "item_type": p.item_type,
                "description": p.description,
            }
            for p in PARSERS.values()
        ],
        "item_types": [{"name": t.name, "description": t.description} for t in ITEM_TYPES.values()],
    }


@router.patch("/system/settings")
async def update_settings(
    payload: SettingsUpdate, actor: Configurer, app_settings: SettingsServiceDep
) -> dict[str, Any]:
    await app_settings.update(actor, payload.values)
    return {"settings": await app_settings.describe()}
