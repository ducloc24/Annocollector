import uuid
from datetime import timedelta

from app.core.clock import Clock, utcnow
from app.core.exceptions import (
    AppError,
    ConflictError,
    ForbiddenError,
    InvalidStateError,
    NotFoundError,
)
from app.core.rbac_catalog import ProjectRole
from app.domain.job_state import ensure_transition
from app.models.ops import Appeal, AppealOutcome, AppealStatus
from app.models.user import User
from app.models.work import Decision, Job, JobStatus, Review, ReviewKind
from app.repositories.ops import OpsRepository
from app.repositories.work import WorkRepository
from app.services.audit import AuditService
from app.services.settings import SettingsService

REVIEW_KINDS = (ReviewKind.REVIEW, ReviewKind.ESCALATION_DECISION, ReviewKind.OVERRIDE)


class AppealService:
    def __init__(
        self,
        ops: OpsRepository,
        work: WorkRepository,
        settings: SettingsService,
        audit: AuditService,
        clock: Clock = utcnow,
    ) -> None:
        self.ops = ops
        self.work = work
        self.settings = settings
        self.audit = audit
        self.clock = clock

    async def _job(self, job_id: uuid.UUID) -> Job:
        job = await self.work.get_job(job_id, lock=True)
        if job is None:
            raise NotFoundError("Job not found")
        return job

    # ---------- override ----------

    async def override(
        self,
        actor: User,
        project_id: uuid.UUID,
        job_id: uuid.UUID,
        decision: str,
        reason: str,
        *,
        kind: str = ReviewKind.OVERRIDE,
    ) -> Job:
        """Replace a reviewer's decision with a new review row; the old one is kept."""
        job = await self._job(job_id)
        if job.project_id != project_id:
            raise NotFoundError("Job not found")
        if decision not in (Decision.ACCEPT, Decision.REJECT):
            raise AppError("Decision must be accept or reject", code="invalid_decision")
        if not reason.strip():
            raise AppError("A reason is required", code="reason_required")
        final = JobStatus.ACCEPTED if decision == Decision.ACCEPT else JobStatus.REJECTED
        if job.status == final or (
            final == JobStatus.ACCEPTED and job.status == JobStatus.ACCEPTED_WITH_FIX
        ):
            raise InvalidStateError("The job is already in that state", code="no_change")
        ensure_transition(job.status, final)
        previous = await self.ops.last_review(job.id, REVIEW_KINDS)
        await self.work.add(
            Review(
                id=uuid.uuid4(),
                job_id=job.id,
                submission_id=previous.submission_id if previous else None,
                reviewer_id=actor.id,
                kind=kind,
                decision=decision,
                reason=reason,
                supersedes_review_id=previous.id if previous else None,
            )
        )
        before = job.status
        job.status = final
        if final == JobStatus.ACCEPTED:
            job.closed_at = self.clock()
        else:
            job.closed_at = None
            job.reviewer_id = None
        await self.audit.record(
            actor=actor,
            action="job.override",
            target_type="job",
            target_id=job.id,
            project_id=project_id,
            before={"status": before},
            after={"status": job.status},
            reason=reason,
        )
        return job

    # ---------- appeals ----------

    async def open(self, user: User, job_id: uuid.UUID, reason: str) -> Appeal:
        job = await self._job(job_id)
        if job.assignee_id != user.id:
            raise NotFoundError("Job not found")
        if job.status != JobStatus.REJECTED:
            raise InvalidStateError("Only a rejected job can be appealed", code="not_appealable")
        if await self.ops.open_appeal_for_job(job.id):
            raise ConflictError("This job already has an open appeal", code="appeal_exists")
        review = await self.ops.last_review(job.id, REVIEW_KINDS)
        if review is None:
            raise InvalidStateError("There is no decision to appeal", code="not_appealable")
        window = timedelta(days=await self.settings.get("appeal_window_days"))
        if self.clock() - review.created_at > window:
            raise ConflictError("The appeal window has passed", code="appeal_window_closed")
        appeal = await self.ops.add(
            Appeal(
                id=uuid.uuid4(),
                job_id=job.id,
                project_id=job.project_id,
                review_id=review.id,
                opened_by=user.id,
                reason=reason,
                status=AppealStatus.OPEN,
            )
        )
        await self.audit.record(
            actor=user,
            action="appeal.open",
            target_type="appeal",
            target_id=appeal.id,
            project_id=job.project_id,
            reason=reason,
        )
        return appeal

    async def decide(
        self,
        actor: User,
        actor_roles: set[str],
        appeal_id: uuid.UUID,
        action: str,
        resolution: str,
    ) -> Appeal:
        """action: upheld | overturned | forward. Managers may forward; only owners go last."""
        appeal = await self.ops.get_appeal(appeal_id)
        if appeal is None:
            raise NotFoundError("Appeal not found")
        if appeal.status == AppealStatus.CLOSED:
            raise InvalidStateError("The appeal is already closed", code="appeal_closed")
        if not resolution.strip():
            raise AppError("A resolution note is required", code="reason_required")
        is_owner = ProjectRole.OWNER in actor_roles
        if appeal.status == AppealStatus.PO_DECISION and not is_owner:
            raise ForbiddenError("Only an owner can decide a forwarded appeal")
        if action == "forward":
            if appeal.status != AppealStatus.OPEN:
                raise InvalidStateError("The appeal was already forwarded")
            appeal.status = AppealStatus.PO_DECISION
            appeal.resolution = resolution
            await self.audit.record(
                actor=actor,
                action="appeal.forward",
                target_type="appeal",
                target_id=appeal.id,
                project_id=appeal.project_id,
                reason=resolution,
            )
            return appeal
        if action not in (AppealOutcome.UPHELD, AppealOutcome.OVERTURNED):
            raise AppError("Unknown action", code="invalid_decision")
        if action == AppealOutcome.OVERTURNED:
            await self.override(
                actor,
                appeal.project_id,
                appeal.job_id,
                Decision.ACCEPT,
                resolution,
                kind=ReviewKind.APPEAL_DECISION,
            )
        appeal.status = AppealStatus.CLOSED
        appeal.outcome = action
        appeal.resolution = resolution
        appeal.resolved_by = actor.id
        appeal.resolved_at = self.clock()
        await self.audit.record(
            actor=actor,
            action=f"appeal.{action}",
            target_type="appeal",
            target_id=appeal.id,
            project_id=appeal.project_id,
            reason=resolution,
        )
        return appeal
