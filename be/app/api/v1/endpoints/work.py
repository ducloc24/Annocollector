import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response, status

from app.api.deps import (
    AuthorizationDep,
    CurrentUser,
    PageParamsDep,
    ProgressServiceDep,
    ProjectAccess,
    ProjectRepositoryDep,
    TaskServiceDep,
    WorkRepositoryDep,
    WorkServiceDep,
    require_project_permission,
)
from app.core.clock import utcnow
from app.core.exceptions import NotFoundError
from app.core.rbac_catalog import Perm
from app.models.user import User
from app.models.work import Job, JobStatus, Task
from app.schemas.common import Page
from app.schemas.user import UserSummary
from app.schemas.work import (
    DraftRequest,
    EscalationDecisionRequest,
    JobRead,
    PairsRequest,
    ReReviewRequest,
    ReviewRequest,
    ReviewResult,
    SubmitRequest,
    SubmitResult,
    TaskCreate,
    TaskCreated,
    TaskRead,
    TaskTeam,
    TaskUpdate,
)
from app.services.work import JobContext

router = APIRouter(tags=["work"])

Member = Annotated[ProjectAccess, require_project_permission(None)]
TaskManager = Annotated[ProjectAccess, require_project_permission(Perm.TASK_MANAGE)]
Assigner = Annotated[ProjectAccess, require_project_permission(Perm.JOB_ASSIGN)]
ProgressReader = Annotated[ProjectAccess, require_project_permission(Perm.PROGRESS_READ)]
Acceptor = Annotated[ProjectAccess, require_project_permission(Perm.TASK_ACCEPT)]
Decider = Annotated[ProjectAccess, require_project_permission(Perm.APPEAL_DECIDE)]
Annotator = Annotated[ProjectAccess, require_project_permission(Perm.JOB_ANNOTATE)]
Reviewer = Annotated[ProjectAccess, require_project_permission(Perm.JOB_REVIEW)]


def _task_read(task: Task, counts: dict[str, int]) -> TaskRead:
    return TaskRead(
        id=task.id,
        name=task.name,
        status=task.status,
        priority=task.priority,
        team_id=task.team_id,
        dataset_version_id=task.dataset_version_id,
        job_config_id=task.job_config_id,
        guideline_version_id=task.guideline_version_id,
        created_at=task.created_at,
        delivered_at=task.delivered_at,
        jobs_total=sum(counts.values()),
        by_status=counts,
    )


def _errors_of(ctx: JobContext, review_id: uuid.UUID) -> list[dict[str, Any]]:
    return [
        {
            "item_id": str(e.item_id),
            "target": e.target,
            "reason_code": e.reason_code,
            "severity": e.severity,
            "note": e.note,
        }
        for e in ctx.review_errors
        if e.review_id == review_id
    ]


def job_view(ctx: JobContext, *, include_draft: bool, include_rounds: bool) -> dict[str, Any]:
    job = ctx.job
    last_review = next((r for r in reversed(ctx.reviews) if r.kind != "re_review"), None)
    view: dict[str, Any] = {
        "job": JobRead.model_validate(job).model_dump(mode="json"),
        "task": {"id": str(ctx.task.id), "name": ctx.task.name},
        "guideline": {"version": ctx.guideline.version, "content": ctx.guideline.content},
        "config": {
            "version": ctx.config.version,
            "item_type": ctx.config.item_type,
            "label_schema": ctx.config.label_schema,
            "self_check": ctx.config.self_check,
            "max_rework": ctx.config.job_rules.get("max_rework"),
        },
        "rework_remaining": max(
            0, int(ctx.config.job_rules.get("max_rework", 0)) - job.rework_count
        ),
        "reason_codes": [
            {
                "code": c.code,
                "label": c.label,
                "default_severity": c.default_severity,
                "applies_to": c.applies_to,
            }
            for c in ctx.reason_codes
            if c.active
        ],
        "items": [
            {
                "id": str(i.id),
                "ordinal": i.ordinal,
                "external_ref": i.external_ref,
                "payload": i.payload,
            }
            for i in ctx.items
        ],
        "draft": job.draft if include_draft else None,
        "last_review": None,
    }
    if last_review is not None:
        view["last_review"] = {
            "decision": last_review.decision,
            "reason": last_review.reason,
            "created_at": last_review.created_at.isoformat(),
            "errors": _errors_of(ctx, last_review.id),
        }
    if include_rounds:
        rounds = []
        for s in ctx.submissions:
            review = next(
                (r for r in ctx.reviews if r.submission_id == s.id and r.kind == "review"), None
            )
            rounds.append(
                {
                    "round": s.round,
                    "submitted_at": s.submitted_at.isoformat(),
                    "annotations": [
                        {
                            "item_id": str(a.item_id),
                            "target": a.target,
                            "value": a.value,
                            "is_unsure": a.is_unsure,
                        }
                        for a in ctx.annotations
                        if a.submission_id == s.id
                    ],
                    "review": None
                    if review is None
                    else {
                        "decision": review.decision,
                        "reason": review.reason,
                        "errors": _errors_of(ctx, review.id),
                    },
                }
            )
        view["rounds"] = rounds
    return view


# ---------- tasks ----------


@router.get("/projects/{project_id}/tasks", response_model=list[TaskRead])
async def list_tasks(access: Member, work: WorkRepositoryDep) -> list[TaskRead]:
    tasks = await work.tasks(access.project_id)
    counts = await work.task_status_counts([t.id for t in tasks])
    return [_task_read(t, counts[t.id]) for t in tasks]


@router.post(
    "/projects/{project_id}/tasks", response_model=TaskCreated, status_code=status.HTTP_201_CREATED
)
async def create_task(
    payload: TaskCreate, access: TaskManager, tasks: TaskServiceDep, work: WorkRepositoryDep
) -> TaskCreated:
    task, jobs = await tasks.create(
        access.user,
        access.project_id,
        name=payload.name,
        dataset_version=payload.dataset_version,
        job_config_version=payload.job_config_version,
        guideline_version=payload.guideline_version,
        team_id=payload.team_id,
        priority=payload.priority,
    )
    counts = await work.task_status_counts([task.id])
    return TaskCreated(task=_task_read(task, counts[task.id]), jobs=jobs)


@router.get("/projects/{project_id}/tasks/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: uuid.UUID, access: Member, tasks: TaskServiceDep, work: WorkRepositoryDep
) -> TaskRead:
    task = await tasks.get(access.project_id, task_id)
    return _task_read(task, (await work.task_status_counts([task.id]))[task.id])


@router.patch("/projects/{project_id}/tasks/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    access: TaskManager,
    tasks: TaskServiceDep,
    work: WorkRepositoryDep,
) -> TaskRead:
    task = await tasks.update(
        access.user, access.project_id, task_id, payload.model_dump(exclude_unset=True)
    )
    return _task_read(task, (await work.task_status_counts([task.id]))[task.id])


@router.post("/projects/{project_id}/tasks/{task_id}/team", response_model=TaskRead)
async def set_task_team(
    task_id: uuid.UUID,
    payload: TaskTeam,
    access: TaskManager,
    tasks: TaskServiceDep,
    work: WorkRepositoryDep,
) -> TaskRead:
    task = await tasks.set_team(access.user, access.project_id, task_id, payload.team_id)
    return _task_read(task, (await work.task_status_counts([task.id]))[task.id])


@router.post("/projects/{project_id}/tasks/{task_id}/activate", response_model=TaskRead)
async def activate_task(
    task_id: uuid.UUID, access: TaskManager, tasks: TaskServiceDep, work: WorkRepositoryDep
) -> TaskRead:
    task = await tasks.activate(access.user, access.project_id, task_id)
    return _task_read(task, (await work.task_status_counts([task.id]))[task.id])


# ---------- progress and acceptance ----------


@router.get("/projects/{project_id}/progress")
async def progress(
    access: ProgressReader, progress: ProgressServiceDep, task_id: uuid.UUID | None = None
) -> dict[str, Any]:
    return await progress.progress(access.project_id, task_id)


@router.get("/projects/{project_id}/tasks/{task_id}/acceptance")
async def acceptance(
    task_id: uuid.UUID, access: Acceptor, tasks: TaskServiceDep, progress: ProgressServiceDep
) -> dict[str, Any]:
    return await progress.acceptance(await tasks.get(access.project_id, task_id))


@router.post("/projects/{project_id}/tasks/{task_id}/sign-off", response_model=TaskRead)
async def sign_off(
    task_id: uuid.UUID,
    access: Acceptor,
    tasks: TaskServiceDep,
    progress: ProgressServiceDep,
    work: WorkRepositoryDep,
) -> TaskRead:
    task = await progress.sign_off(access.user, await tasks.get(access.project_id, task_id))
    return _task_read(task, (await work.task_status_counts([task.id]))[task.id])


@router.post("/projects/{project_id}/tasks/{task_id}/re-review")
async def re_review(
    task_id: uuid.UUID,
    payload: ReReviewRequest,
    access: Acceptor,
    tasks: TaskServiceDep,
    jobs: WorkServiceDep,
) -> dict[str, int]:
    task = await tasks.get(access.project_id, task_id)
    return {
        "reopened": await jobs.reopen(
            access.user, access.project_id, task, payload.job_ids, payload.reason
        )
    }


# ---------- jobs (coordination) ----------


@router.get("/projects/{project_id}/jobs", response_model=Page[JobRead])
async def list_jobs(
    access: Assigner,
    work: WorkRepositoryDep,
    page: PageParamsDep,
    status_filter: Annotated[JobStatus | None, Query(alias="status")] = None,
    task_id: uuid.UUID | None = None,
    assignee_id: uuid.UUID | None = None,
    reviewer_id: uuid.UUID | None = None,
    stuck: bool = False,
) -> Page[JobRead]:
    from datetime import timedelta

    jobs, total = await work.list_jobs(
        access.project_id,
        status=status_filter,
        task_id=task_id,
        assignee_id=assignee_id,
        reviewer_id=reviewer_id,
        stuck_before=utcnow() - timedelta(hours=24) if stuck else None,
        offset=page.offset,
        limit=page.limit,
    )
    return Page[JobRead](
        items=[JobRead.model_validate(j) for j in jobs],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/projects/{project_id}/workload")
async def workload(
    access: Assigner, work: WorkRepositoryDep, repo: ProjectRepositoryDep
) -> list[dict[str, Any]]:
    rows = await work.workload(access.project_id)
    team_rows = await repo.team_roles_in_project(access.project_id, utcnow())
    people = {u for u, _, _ in team_rows}
    result: dict[uuid.UUID, dict[str, Any]] = {
        u: {
            "user_id": str(u),
            "annotate": 0,
            "review": 0,
            "roles": sorted({r for uu, r, _ in team_rows if uu == u}),
        }
        for u in people
    }
    for user_id, kind, count in rows:
        result.setdefault(
            user_id, {"user_id": str(user_id), "annotate": 0, "review": 0, "roles": []}
        )[kind] = count
    users = {u.id: u for u in [await repo.session.get(User, uid) for uid in result] if u}
    return [
        {**row, "user": UserSummary.model_validate(users[uid]).model_dump(mode="json")}
        for uid, row in result.items()
        if uid in users
    ]


@router.post("/projects/{project_id}/jobs/assign", response_model=list[JobRead])
async def assign_jobs(
    payload: PairsRequest, access: Assigner, jobs: WorkServiceDep
) -> list[JobRead]:
    done = await jobs.assign(
        access.user, access.project_id, [(p.job_id, p.user_id) for p in payload.assignments]
    )
    return [JobRead.model_validate(j) for j in done]


@router.post("/projects/{project_id}/jobs/reviewers", response_model=list[JobRead])
async def set_reviewers(
    payload: PairsRequest, access: Assigner, jobs: WorkServiceDep
) -> list[JobRead]:
    done = await jobs.set_reviewers(
        access.user, access.project_id, [(p.job_id, p.user_id) for p in payload.assignments]
    )
    return [JobRead.model_validate(j) for j in done]


@router.post("/projects/{project_id}/jobs/{job_id}/unassign", response_model=JobRead)
async def unassign_job(job_id: uuid.UUID, access: Assigner, jobs: WorkServiceDep) -> JobRead:
    return JobRead.model_validate(await jobs.unassign(access.user, access.project_id, job_id))


@router.get("/projects/{project_id}/escalations", response_model=list[JobRead])
async def escalations(access: Decider, work: WorkRepositoryDep) -> list[JobRead]:
    jobs, _ = await work.list_jobs(
        access.project_id,
        status=JobStatus.ESCALATED,
        task_id=None,
        assignee_id=None,
        reviewer_id=None,
        stuck_before=None,
        offset=0,
        limit=500,
    )
    return [JobRead.model_validate(j) for j in jobs]


@router.post("/projects/{project_id}/jobs/{job_id}/escalation-decision", response_model=JobRead)
async def escalation_decision(
    job_id: uuid.UUID, payload: EscalationDecisionRequest, access: Decider, jobs: WorkServiceDep
) -> JobRead:
    job = await jobs.escalation_decision(
        access.user,
        access.project_id,
        job_id,
        payload.decision,
        payload.reason,
        payload.guideline_issue,
    )
    return JobRead.model_validate(job)


# ---------- next job (pull) ----------


@router.post("/projects/{project_id}/jobs/next", response_model=None)
async def next_job(access: Annotator, jobs: WorkServiceDep) -> Response | dict[str, Any]:
    job = await jobs.next_job(access.user, access.project_id)
    if job is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return job_view(await jobs.context(job, history=True), include_draft=True, include_rounds=False)


@router.post("/projects/{project_id}/reviews/next", response_model=None)
async def next_review(access: Reviewer, jobs: WorkServiceDep) -> Response | dict[str, Any]:
    job = await jobs.next_review(access.user, access.project_id)
    if job is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return job_view(await jobs.context(job, history=True), include_draft=False, include_rounds=True)


# ---------- one job ----------


async def _job_access(job: Job, user: User, authz) -> str:
    """'annotator' | 'reviewer' | 'coordinator'; anyone else gets 404."""
    perms = await authz.project_permissions(user.id, job.project_id)
    if job.assignee_id == user.id and Perm.JOB_ANNOTATE in perms:
        return "annotator"
    if job.reviewer_id == user.id and Perm.JOB_REVIEW in perms:
        return "reviewer"
    if Perm.JOB_ASSIGN in perms or Perm.APPEAL_DECIDE in perms or Perm.TASK_ACCEPT in perms:
        return "coordinator"
    raise NotFoundError("Job not found")


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: uuid.UUID, user: CurrentUser, jobs: WorkServiceDep, authz: AuthorizationDep
) -> dict[str, Any]:
    job = await jobs.job(job_id)
    role = await _job_access(job, user, authz)
    view = job_view(
        await jobs.context(job, history=True),
        include_draft=role == "annotator",
        include_rounds=role != "annotator",
    )
    view["my_role"] = role
    return view


@router.get("/jobs/{job_id}/review-context")
async def review_context(
    job_id: uuid.UUID, user: CurrentUser, jobs: WorkServiceDep, authz: AuthorizationDep
) -> dict[str, Any]:
    job = await jobs.job(job_id)
    role = await _job_access(job, user, authz)
    if role == "annotator":
        raise NotFoundError("Job not found")
    view = job_view(await jobs.context(job, history=True), include_draft=False, include_rounds=True)
    view["my_role"] = role
    return view


@router.post("/jobs/{job_id}/start", response_model=JobRead)
async def start_job(job_id: uuid.UUID, user: CurrentUser, jobs: WorkServiceDep) -> JobRead:
    return JobRead.model_validate(await jobs.start(user, job_id))


@router.put("/jobs/{job_id}/draft", response_model=JobRead)
async def save_draft(
    job_id: uuid.UUID, payload: DraftRequest, user: CurrentUser, jobs: WorkServiceDep
) -> JobRead:
    return JobRead.model_validate(await jobs.save_draft(user, job_id, payload.draft))


@router.post("/jobs/{job_id}/submit", response_model=SubmitResult)
async def submit_job(
    job_id: uuid.UUID, payload: SubmitRequest, user: CurrentUser, jobs: WorkServiceDep
) -> SubmitResult:
    submission = await jobs.submit(
        user, job_id, [a.model_dump(mode="json") for a in payload.annotations], payload.self_check
    )
    return SubmitResult(job_id=job_id, status=JobStatus.SUBMITTED, round=submission.round)


@router.post("/jobs/{job_id}/review/start", response_model=JobRead)
async def start_review(job_id: uuid.UUID, user: CurrentUser, jobs: WorkServiceDep) -> JobRead:
    return JobRead.model_validate(await jobs.start_review(user, job_id))


@router.post(
    "/jobs/{job_id}/reviews", response_model=ReviewResult, status_code=status.HTTP_201_CREATED
)
async def review_job(
    job_id: uuid.UUID, payload: ReviewRequest, user: CurrentUser, jobs: WorkServiceDep
) -> ReviewResult:
    review, job = await jobs.decide(
        user,
        job_id,
        payload.decision,
        payload.reason,
        [e.model_dump(mode="json") for e in payload.errors],
    )
    return ReviewResult(review_id=review.id, job_status=job.status, rework_count=job.rework_count)
