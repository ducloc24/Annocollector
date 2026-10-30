import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from app.core.clock import Clock, utcnow
from app.core.exceptions import (
    AppError,
    ConflictError,
    ForbiddenError,
    InvalidStateError,
    NotFoundError,
)
from app.domain import label_schema
from app.domain.item_types import get_item_type
from app.domain.job_state import ensure_transition
from app.domain.quality import should_review
from app.models.project import GuidelineVersion, Item, ProjectStatus, ReasonCode
from app.models.user import User
from app.models.work import (
    Annotation,
    Decision,
    Job,
    JobConfig,
    JobStatus,
    Review,
    ReviewError,
    ReviewKind,
    Submission,
    Task,
    TaskStatus,
)
from app.repositories.project import ProjectRepository
from app.repositories.work import WorkRepository
from app.services.audit import AuditService

SEVERITIES = ("critical", "major", "minor")
REVIEW_DECISIONS = (Decision.ACCEPT, Decision.ACCEPT_WITH_FIX, Decision.REJECT, Decision.ESCALATE)


class WipLimitError(ConflictError):
    code = "wip_limit_reached"


class LeaseExpiredError(ConflictError):
    code = "lease_expired"


@dataclass
class JobContext:
    job: Job
    task: Task
    config: JobConfig
    guideline: GuidelineVersion
    items: list[Item]
    reason_codes: list[ReasonCode]
    submissions: list[Submission] = field(default_factory=list)
    annotations: list[Annotation] = field(default_factory=list)
    reviews: list[Review] = field(default_factory=list)
    review_errors: list[ReviewError] = field(default_factory=list)


def codes_for(codes: list[ReasonCode], use: str) -> set[str]:
    return {c.code for c in codes if c.active and c.applies_to in (use, "both")}


def validate_submission(
    config: JobConfig, items: list[Item], annotations: list[dict[str, Any]], label_codes: set[str]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Check every target of every item is labelled exactly once and each label is valid."""
    item_type = get_item_type(config.item_type)
    if item_type is None:
        return [], [f"Unknown item type {config.item_type}"]
    expected = {(str(i.id), t) for i in items for t in item_type.targets(i.payload)}
    seen: set[tuple[str, str]] = set()
    cleaned: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, a in enumerate(annotations):
        key = (str(a.get("item_id")), str(a.get("target")))
        if key not in expected:
            errors.append(f"annotations[{index}] targets an unknown item or step")
            continue
        if key in seen:
            errors.append(f"annotations[{index}] labels {key[1]} twice")
            continue
        seen.add(key)
        value, problems = label_schema.validate_value(
            config.label_schema, a.get("value"), label_codes
        )
        errors += [f"{key[1]}: {p}" for p in problems]
        cleaned.append(
            {
                "item_id": key[0],
                "target": key[1],
                "value": value,
                "is_unsure": label_schema.is_unsure(config.label_schema, value),
            }
        )
    missing = expected - seen
    if missing:
        errors.append(
            f"{len(missing)} step(s) are not labelled: "
            + ", ".join(sorted(t for _, t in missing))[:300]
        )
    return cleaned, errors


class WorkService:
    def __init__(
        self,
        projects: ProjectRepository,
        work: WorkRepository,
        audit: AuditService,
        clock: Clock = utcnow,
    ) -> None:
        self.projects = projects
        self.work = work
        self.audit = audit
        self.clock = clock

    # ---------- helpers ----------

    async def team_ids(
        self, user_id: uuid.UUID, project_id: uuid.UUID, role: str
    ) -> list[uuid.UUID]:
        rows = await self.projects.team_roles_in_project(project_id, self.clock())
        return [team for user, r, team in rows if user == user_id and r == role]

    async def job(self, job_id: uuid.UUID, *, lock: bool = False) -> Job:
        job = await self.work.get_job(job_id, lock=lock)
        if job is None:
            raise NotFoundError("Job not found")
        return job

    async def context(self, job: Job, *, history: bool = False) -> JobContext:
        task = await self.work.get_task(job.task_id)
        config = await self.work.get_job_config(job.job_config_id)
        guideline = await self.projects.session.get(GuidelineVersion, job.guideline_version_id)
        assert task and config and guideline
        ctx = JobContext(
            job=job,
            task=task,
            config=config,
            guideline=guideline,
            items=await self.work.job_items(job.id),
            reason_codes=await self.projects.reason_codes(job.project_id),
        )
        if history:
            ctx.submissions = await self.work.submissions(job.id)
            ctx.annotations = await self.work.annotations([s.id for s in ctx.submissions])
            ctx.reviews = await self.work.reviews(job.id)
            ctx.review_errors = await self.work.review_errors([r.id for r in ctx.reviews])
        return ctx

    async def _project_active(self, project_id: uuid.UUID) -> None:
        project = await self.projects.get(project_id)
        if project is None or project.status != ProjectStatus.ACTIVE:
            raise ConflictError("Project is not active", code="project_not_active")

    def _set_status(self, job: Job, target: JobStatus) -> None:
        ensure_transition(job.status, target)
        job.status = target

    async def _config(self, job: Job) -> JobConfig:
        config = await self.work.get_job_config(job.job_config_id)
        assert config is not None
        return config

    # ---------- annotator ----------

    async def next_job(self, user: User, project_id: uuid.UUID) -> Job | None:
        await self._project_active(project_id)
        teams = await self.team_ids(user.id, project_id, "annotator")
        if not teams:
            raise ForbiddenError("You are not an annotator in this project")
        now = self.clock()
        await self.work.release_expired_leases(project_id, now)
        job = await self.work.pickable_job(project_id=project_id, team_ids=teams, user_id=user.id)
        if job is None:
            return None
        config = await self._config(job)
        if config.job_rules.get("assignment_mode") == "push_only" and job.assignee_id != user.id:
            return None
        limit = int(config.job_rules["wip_limit_annotator"])
        if (
            await self.work.count_jobs(
                assignee_id=user.id, status=JobStatus.IN_PROGRESS, project_id=project_id
            )
            >= limit
        ):
            raise WipLimitError(
                f"You already hold {limit} jobs in progress", details={"limit": limit}
            )
        await self._start(user, job, config)
        return job

    async def _start(self, user: User, job: Job, config: JobConfig) -> None:
        now = self.clock()
        self._set_status(job, JobStatus.IN_PROGRESS)
        job.assignee_id = user.id
        job.assigned_at = job.assigned_at or now
        job.lease_expires_at = now + timedelta(minutes=int(config.job_rules["lease_minutes"]))
        await self.audit.record(
            actor=user,
            action="job.start",
            target_type="job",
            target_id=job.id,
            project_id=job.project_id,
        )

    async def start(self, user: User, job_id: uuid.UUID) -> Job:
        job = await self.job(job_id, lock=True)
        if job.assignee_id != user.id:
            raise NotFoundError("Job not found")
        if job.status == JobStatus.IN_PROGRESS:
            return job
        await self._project_active(job.project_id)
        await self._start(user, job, await self._config(job))
        return job

    def _check_lease(self, job: Job) -> None:
        if job.lease_expires_at is not None and job.lease_expires_at < self.clock():
            job.status = JobStatus.UNASSIGNED
            job.assignee_id = None
            job.lease_expires_at = None
            job.draft = None
            raise LeaseExpiredError("Your lease expired and the job went back to the pool")

    async def save_draft(self, user: User, job_id: uuid.UUID, draft: dict[str, Any]) -> Job:
        job = await self.job(job_id, lock=True)
        if job.assignee_id != user.id or job.status != JobStatus.IN_PROGRESS:
            raise InvalidStateError("Only your job in progress can be saved")
        self._check_lease(job)
        config = await self._config(job)
        now = self.clock()
        job.draft = draft
        job.draft_updated_at = now
        job.lease_expires_at = now + timedelta(minutes=int(config.job_rules["lease_minutes"]))
        return job

    async def submit(
        self,
        user: User,
        job_id: uuid.UUID,
        annotations: list[dict[str, Any]],
        self_check: list[bool],
    ) -> Submission:
        job = await self.job(job_id, lock=True)
        if job.assignee_id != user.id:
            raise NotFoundError("Job not found")
        if job.status != JobStatus.IN_PROGRESS:
            raise InvalidStateError("Job is not in progress", details={"status": job.status})
        self._check_lease(job)
        ctx = await self.context(job)
        if len(self_check) != len(ctx.config.self_check) or not all(self_check):
            raise AppError("Answer every self-check question", code="self_check_incomplete")
        cleaned, errors = validate_submission(
            ctx.config, ctx.items, annotations, codes_for(ctx.reason_codes, "label")
        )
        if errors:
            code = (
                "annotation_incomplete"
                if any("not labelled" in e for e in errors)
                else "annotation_invalid"
            )
            raise AppError("Labels are not valid", code=code, details={"errors": errors})
        now = self.clock()
        previous = await self.work.submissions(job.id)
        submission = await self.work.add(
            Submission(
                id=uuid.uuid4(),
                job_id=job.id,
                round=len(previous) + 1,
                annotator_id=user.id,
                self_check_result=self_check,
                submitted_at=now,
            )
        )
        await self.work.add_all(
            [
                Annotation(
                    id=uuid.uuid4(),
                    submission_id=submission.id,
                    item_id=uuid.UUID(a["item_id"]),
                    target=a["target"],
                    value=a["value"],
                    is_unsure=a["is_unsure"],
                )
                for a in cleaned
            ]
        )
        self._set_status(job, JobStatus.SUBMITTED)
        job.submitted_at = now
        job.has_unsure = any(a["is_unsure"] for a in cleaned)
        job.lease_expires_at = None
        job.draft = None
        job.draft_updated_at = None
        if not should_review(
            float(ctx.config.job_rules.get("review_rate", 1.0)),
            is_gold=job.is_gold,
            has_unsure=job.has_unsure,
            rework_count=job.rework_count,
        ):
            # Not picked for review: accepted straight away, with a row that says so.
            self._set_status(job, JobStatus.ACCEPTED)
            job.closed_at = now
            await self.work.add(
                Review(
                    id=uuid.uuid4(),
                    job_id=job.id,
                    submission_id=submission.id,
                    reviewer_id=None,
                    kind=ReviewKind.AUTO_ACCEPT,
                    decision=Decision.ACCEPT,
                    reason="Không được chọn vào mẫu review",
                )
            )
        await self.audit.record(
            actor=user,
            action="job.submit",
            target_type="job",
            target_id=job.id,
            project_id=job.project_id,
            after={"round": submission.round},
        )
        return submission

    # ---------- coordinator (push) ----------

    async def _annotator_of_task(self, task: Task, user_id: uuid.UUID, role: str) -> None:
        if task.team_id is None or task.team_id not in await self.team_ids(
            user_id, task.project_id, role
        ):
            raise ConflictError(
                f"The person is not a {role} in this task's team", code="not_in_task_team"
            )

    async def assign(
        self, actor: User, project_id: uuid.UUID, pairs: list[tuple[uuid.UUID, uuid.UUID]]
    ) -> list[Job]:
        jobs = []
        now = self.clock()
        for job_id, assignee_id in pairs:
            job = await self.job(job_id, lock=True)
            if job.project_id != project_id:
                raise NotFoundError("Job not found")
            task = await self.work.get_task(job.task_id)
            assert task is not None
            await self._annotator_of_task(task, assignee_id, "annotator")
            if job.status not in (
                JobStatus.UNASSIGNED,
                JobStatus.ASSIGNED,
                JobStatus.IN_PROGRESS,
                JobStatus.REJECTED,
            ):
                raise InvalidStateError(
                    "Job cannot be reassigned now", details={"status": job.status}
                )
            before = job.assignee_id
            if job.status == JobStatus.REJECTED and before == assignee_id:
                jobs.append(job)
                continue
            if job.status == JobStatus.REJECTED:
                job.status = JobStatus.ASSIGNED
            else:
                self._set_status(job, JobStatus.ASSIGNED)
            job.assignee_id = assignee_id
            job.assigned_at = now
            job.lease_expires_at = None
            job.draft = None
            await self.audit.record(
                actor=actor,
                action="job.assign",
                target_type="job",
                target_id=job.id,
                project_id=project_id,
                before={"assignee_id": str(before) if before else None},
                after={"assignee_id": str(assignee_id)},
            )
            jobs.append(job)
        return jobs

    async def unassign(self, actor: User, project_id: uuid.UUID, job_id: uuid.UUID) -> Job:
        job = await self.job(job_id, lock=True)
        if job.project_id != project_id:
            raise NotFoundError("Job not found")
        if job.status not in (JobStatus.ASSIGNED, JobStatus.IN_PROGRESS, JobStatus.REJECTED):
            raise InvalidStateError(
                "Job has no annotator to remove", details={"status": job.status}
            )
        before = job.assignee_id
        job.status = JobStatus.UNASSIGNED
        job.assignee_id = None
        job.lease_expires_at = None
        job.draft = None
        await self.audit.record(
            actor=actor,
            action="job.unassign",
            target_type="job",
            target_id=job.id,
            project_id=project_id,
            before={"assignee_id": str(before) if before else None},
        )
        return job

    async def set_reviewers(
        self, actor: User, project_id: uuid.UUID, pairs: list[tuple[uuid.UUID, uuid.UUID]]
    ) -> list[Job]:
        jobs = []
        for job_id, reviewer_id in pairs:
            job = await self.job(job_id, lock=True)
            if job.project_id != project_id:
                raise NotFoundError("Job not found")
            if reviewer_id == job.assignee_id:
                raise ForbiddenError(
                    "A reviewer cannot review their own work", code="self_review_forbidden"
                )
            task = await self.work.get_task(job.task_id)
            assert task is not None
            await self._annotator_of_task(task, reviewer_id, "reviewer")
            if job.status == JobStatus.IN_REVIEW:
                raise InvalidStateError("Job is already being reviewed")
            job.reviewer_id = reviewer_id
            await self.audit.record(
                actor=actor,
                action="job.set_reviewer",
                target_type="job",
                target_id=job.id,
                project_id=project_id,
                after={"reviewer_id": str(reviewer_id)},
            )
            jobs.append(job)
        return jobs

    # ---------- reviewer ----------

    async def next_review(self, user: User, project_id: uuid.UUID) -> Job | None:
        await self._project_active(project_id)
        teams = await self.team_ids(user.id, project_id, "reviewer")
        if not teams:
            raise ForbiddenError("You are not a reviewer in this project")
        job = await self.work.reviewable_job(project_id=project_id, team_ids=teams, user_id=user.id)
        if job is None:
            return None
        config = await self._config(job)
        limit = int(config.job_rules["wip_limit_reviewer"])
        if (
            await self.work.count_jobs(
                reviewer_id=user.id, status=JobStatus.IN_REVIEW, project_id=project_id
            )
            >= limit
        ):
            raise WipLimitError(
                f"You already have {limit} jobs in review", details={"limit": limit}
            )
        self._begin_review(user, job)
        return job

    def _begin_review(self, user: User, job: Job) -> None:
        if job.assignee_id == user.id:
            raise ForbiddenError("You cannot review your own work", code="self_review_forbidden")
        self._set_status(job, JobStatus.IN_REVIEW)
        job.reviewer_id = user.id

    async def start_review(self, user: User, job_id: uuid.UUID) -> Job:
        job = await self.job(job_id, lock=True)
        if job.reviewer_id != user.id:
            raise NotFoundError("Job not found")
        if job.status == JobStatus.IN_REVIEW:
            return job
        self._begin_review(user, job)
        return job

    async def decide(
        self,
        user: User,
        job_id: uuid.UUID,
        decision: str,
        reason: str | None,
        errors: list[dict[str, Any]],
    ) -> tuple[Review, Job]:
        job = await self.job(job_id, lock=True)
        if job.reviewer_id != user.id or job.status != JobStatus.IN_REVIEW:
            raise InvalidStateError("This job is not in review by you")
        if job.assignee_id == user.id:
            raise ForbiddenError("You cannot review your own work", code="self_review_forbidden")
        if decision not in REVIEW_DECISIONS:
            raise AppError("Unknown decision", code="invalid_decision")
        if decision in (Decision.REJECT, Decision.ESCALATE) and not (reason and reason.strip()):
            raise AppError("A reason is required", code="reason_required")
        ctx = await self.context(job)
        item_targets = {}
        item_type = get_item_type(ctx.config.item_type)
        for item in ctx.items:
            item_targets[str(item.id)] = (
                set(item_type.targets(item.payload)) if item_type else set()
            )
        active_codes = {c.code for c in ctx.reason_codes if c.active}
        for index, e in enumerate(errors):
            targets = item_targets.get(str(e.get("item_id")))
            if targets is None or (e.get("target") is not None and e.get("target") not in targets):
                raise AppError(
                    f"errors[{index}] points at an unknown item or step", code="invalid_error"
                )
            if e.get("reason_code") not in active_codes:
                raise AppError(f"errors[{index}] has an unknown reason code", code="invalid_error")
            if e.get("severity") not in SEVERITIES:
                raise AppError(f"errors[{index}] has an invalid severity", code="invalid_error")
        submissions = await self.work.submissions(job.id)
        review = await self.work.add(
            Review(
                id=uuid.uuid4(),
                job_id=job.id,
                submission_id=submissions[-1].id if submissions else None,
                reviewer_id=user.id,
                kind=ReviewKind.REVIEW,
                decision=decision,
                reason=reason,
            )
        )
        await self.work.add_all(
            [
                ReviewError(
                    id=uuid.uuid4(),
                    review_id=review.id,
                    item_id=uuid.UUID(str(e["item_id"])),
                    target=e.get("target"),
                    reason_code=e["reason_code"],
                    severity=e["severity"],
                    note=e.get("note"),
                )
                for e in errors
            ]
        )
        now = self.clock()
        job.last_reviewer_id = user.id
        if decision in (Decision.ACCEPT, Decision.ACCEPT_WITH_FIX):
            self._set_status(
                job,
                JobStatus.ACCEPTED if decision == Decision.ACCEPT else JobStatus.ACCEPTED_WITH_FIX,
            )
            job.closed_at = now
        elif decision == Decision.ESCALATE or job.rework_count >= int(
            ctx.config.job_rules["max_rework"]
        ):
            self._set_status(job, JobStatus.ESCALATED)
        else:
            self._set_status(job, JobStatus.REJECTED)
            job.rework_count += 1
            job.reviewer_id = None
        await self.audit.record(
            actor=user,
            action=f"job.review.{decision}",
            target_type="job",
            target_id=job.id,
            project_id=job.project_id,
            after={"status": job.status, "errors": len(errors)},
            reason=reason,
        )
        return review, job

    async def escalation_decision(
        self,
        actor: User,
        project_id: uuid.UUID,
        job_id: uuid.UUID,
        decision: str,
        reason: str,
        guideline_issue: bool,
    ) -> Job:
        job = await self.job(job_id, lock=True)
        if job.project_id != project_id or job.status != JobStatus.ESCALATED:
            raise InvalidStateError("Job is not escalated")
        if decision not in (Decision.ACCEPT, Decision.REJECT):
            raise AppError("Decision must be accept or reject", code="invalid_decision")
        reviews = await self.work.reviews(job.id)
        await self.work.add(
            Review(
                id=uuid.uuid4(),
                job_id=job.id,
                submission_id=reviews[-1].submission_id if reviews else None,
                reviewer_id=actor.id,
                kind=ReviewKind.ESCALATION_DECISION,
                decision=decision,
                reason=reason,
                guideline_issue=guideline_issue,
                supersedes_review_id=reviews[-1].id if reviews else None,
            )
        )
        if decision == Decision.ACCEPT:
            self._set_status(job, JobStatus.ACCEPTED)
            job.closed_at = self.clock()
        else:
            self._set_status(job, JobStatus.REJECTED)
            job.reviewer_id = None
        await self.audit.record(
            actor=actor,
            action="job.escalation_decision",
            target_type="job",
            target_id=job.id,
            project_id=project_id,
            after={"decision": decision, "guideline_issue": guideline_issue},
            reason=reason,
        )
        return job

    async def reopen(
        self, actor: User, project_id: uuid.UUID, task: Task, job_ids: list[uuid.UUID], reason: str
    ) -> int:
        """Re-review: accepted jobs go back to the review queue."""
        if task.status == TaskStatus.DELIVERED:
            raise InvalidStateError("Task is already delivered", code="task_delivered")
        count = 0
        for job_id in job_ids:
            job = await self.job(job_id, lock=True)
            if job.task_id != task.id:
                raise NotFoundError("Job not found in this task")
            self._set_status(job, JobStatus.SUBMITTED)
            job.closed_at = None
            job.reviewer_id = None
            await self.work.add(
                Review(
                    id=uuid.uuid4(),
                    job_id=job.id,
                    reviewer_id=actor.id,
                    kind=ReviewKind.RE_REVIEW,
                    decision=Decision.REOPEN,
                    reason=reason,
                )
            )
            count += 1
        await self.audit.record(
            actor=actor,
            action="task.re_review",
            target_type="task",
            target_id=task.id,
            project_id=project_id,
            after={"jobs": count},
            reason=reason,
        )
        return count
