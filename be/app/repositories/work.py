import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Item
from app.models.work import (
    Annotation,
    Job,
    JobConfig,
    JobItem,
    JobStatus,
    Review,
    ReviewError,
    Submission,
    Task,
    TaskStatus,
)

OPEN_ANNOTATOR_STATUSES = (JobStatus.ASSIGNED, JobStatus.IN_PROGRESS, JobStatus.REJECTED)


class WorkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, obj):
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def add_all(self, objs: Sequence[Any]) -> None:
        self.session.add_all(objs)
        await self.session.flush()

    # ---------- job configs ----------

    async def job_configs(self, project_id: uuid.UUID) -> list[JobConfig]:
        rows = await self.session.scalars(
            select(JobConfig)
            .where(JobConfig.project_id == project_id)
            .order_by(JobConfig.version.desc())
        )
        return list(rows)

    async def job_config(self, project_id: uuid.UUID, version: int) -> JobConfig | None:
        return await self.session.scalar(
            select(JobConfig).where(
                JobConfig.project_id == project_id, JobConfig.version == version
            )
        )

    async def get_job_config(self, config_id: uuid.UUID) -> JobConfig | None:
        return await self.session.get(JobConfig, config_id)

    # ---------- tasks ----------

    async def tasks(self, project_id: uuid.UUID) -> list[Task]:
        rows = await self.session.scalars(
            select(Task)
            .where(Task.project_id == project_id)
            .order_by(Task.priority.desc(), Task.created_at.desc())
        )
        return list(rows)

    async def get_task(self, task_id: uuid.UUID) -> Task | None:
        return await self.session.get(Task, task_id)

    async def team_has_open_tasks(self, project_id: uuid.UUID, team_id: uuid.UUID) -> bool:
        found = await self.session.scalar(
            select(Task.id).where(
                Task.project_id == project_id,
                Task.team_id == team_id,
                Task.status == TaskStatus.ACTIVE,
            )
        )
        return found is not None

    async def status_counts(
        self, project_id: uuid.UUID, task_id: uuid.UUID | None = None
    ) -> dict[str, int]:
        stmt = select(Job.status, func.count()).where(Job.project_id == project_id)
        if task_id:
            stmt = stmt.where(Job.task_id == task_id)
        rows = await self.session.execute(stmt.group_by(Job.status))
        return {status: count for status, count in rows.tuples()}

    async def task_status_counts(
        self, task_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, dict[str, int]]:
        result: dict[uuid.UUID, dict[str, int]] = {t: {} for t in task_ids}
        if not task_ids:
            return result
        rows = await self.session.execute(
            select(Job.task_id, Job.status, func.count())
            .where(Job.task_id.in_(task_ids))
            .group_by(Job.task_id, Job.status)
        )
        for task_id, status, count in rows.tuples():
            result[task_id][status] = count
        return result

    # ---------- jobs ----------

    async def get_job(self, job_id: uuid.UUID, *, lock: bool = False) -> Job | None:
        stmt = select(Job).where(Job.id == job_id)
        if lock:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def list_jobs(
        self,
        project_id: uuid.UUID,
        *,
        status: str | None,
        task_id: uuid.UUID | None,
        assignee_id: uuid.UUID | None,
        reviewer_id: uuid.UUID | None,
        stuck_before: datetime | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Job], int]:
        stmt = select(Job).where(Job.project_id == project_id)
        if status:
            stmt = stmt.where(Job.status == status)
        if task_id:
            stmt = stmt.where(Job.task_id == task_id)
        if assignee_id:
            stmt = stmt.where(Job.assignee_id == assignee_id)
        if reviewer_id:
            stmt = stmt.where(Job.reviewer_id == reviewer_id)
        if stuck_before:
            stmt = stmt.where(
                Job.status.in_((JobStatus.SUBMITTED, JobStatus.IN_REVIEW, JobStatus.ESCALATED)),
                Job.submitted_at < stuck_before,
            )
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self.session.scalars(
            stmt.order_by(Job.task_id, Job.ordinal).offset(offset).limit(limit)
        )
        return list(rows), total or 0

    async def jobs_for_user(self, user_id: uuid.UUID, statuses: Sequence[str]) -> list[Job]:
        rows = await self.session.scalars(
            select(Job)
            .where(Job.assignee_id == user_id, Job.status.in_(statuses))
            .order_by(Job.updated_at.desc())
        )
        return list(rows)

    async def jobs_in_review_by(self, user_id: uuid.UUID) -> list[Job]:
        rows = await self.session.scalars(
            select(Job)
            .where(
                Job.reviewer_id == user_id,
                Job.status.in_((JobStatus.IN_REVIEW, JobStatus.SUBMITTED)),
            )
            .order_by(Job.submitted_at)
        )
        return list(rows)

    async def count_jobs(
        self,
        *,
        assignee_id: uuid.UUID | None = None,
        reviewer_id: uuid.UUID | None = None,
        status: str,
        project_id: uuid.UUID,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(Job)
            .where(Job.status == status, Job.project_id == project_id)
        )
        if assignee_id:
            stmt = stmt.where(Job.assignee_id == assignee_id)
        if reviewer_id:
            stmt = stmt.where(Job.reviewer_id == reviewer_id)
        return await self.session.scalar(stmt) or 0

    async def pickable_job(
        self,
        *,
        project_id: uuid.UUID,
        team_ids: Sequence[uuid.UUID],
        user_id: uuid.UUID,
    ) -> Job | None:
        """Next job for an annotator, locked with SKIP LOCKED.

        Order: own rejected jobs (rework), jobs a PM assigned to the user, then unassigned
        jobs of active tasks of the user's teams by task priority and age.
        """
        own = await self.session.scalar(
            select(Job)
            .where(
                Job.project_id == project_id,
                Job.assignee_id == user_id,
                Job.status.in_((JobStatus.REJECTED, JobStatus.ASSIGNED)),
            )
            .order_by(case((Job.status == JobStatus.REJECTED, 0), else_=1), Job.updated_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if own is not None or not team_ids:
            return own
        return await self.session.scalar(
            select(Job)
            .join(Task, Task.id == Job.task_id)
            .where(
                Job.project_id == project_id,
                Job.status == JobStatus.UNASSIGNED,
                Task.status == TaskStatus.ACTIVE,
                Task.team_id.in_(team_ids),
            )
            .order_by(Task.priority.desc(), Job.is_gold.desc(), Job.created_at, Job.ordinal)
            .limit(1)
            .with_for_update(of=Job, skip_locked=True)
        )

    async def reviewable_job(
        self,
        *,
        project_id: uuid.UUID,
        team_ids: Sequence[uuid.UUID],
        user_id: uuid.UUID,
    ) -> Job | None:
        """Next submitted job for a reviewer, never one the reviewer annotated."""
        if not team_ids:
            return None
        return await self.session.scalar(
            select(Job)
            .join(Task, Task.id == Job.task_id)
            .where(
                Job.project_id == project_id,
                Job.status == JobStatus.SUBMITTED,
                Task.team_id.in_(team_ids),
                Job.assignee_id != user_id,
                or_(Job.reviewer_id.is_(None), Job.reviewer_id == user_id),
            )
            .order_by(
                case((Job.last_reviewer_id == user_id, 0), else_=1),
                Job.has_unsure.desc(),
                Job.submitted_at,
            )
            .limit(1)
            .with_for_update(of=Job, skip_locked=True)
        )

    async def submitted_count(self, project_id: uuid.UUID, team_ids: Sequence[uuid.UUID]) -> int:
        if not team_ids:
            return 0
        total = await self.session.scalar(
            select(func.count())
            .select_from(Job)
            .join(Task, Task.id == Job.task_id)
            .where(
                Job.project_id == project_id,
                Job.status == JobStatus.SUBMITTED,
                Task.team_id.in_(team_ids),
            )
        )
        return total or 0

    async def release_expired_leases(self, project_id: uuid.UUID, now: datetime) -> None:
        await self.session.execute(
            update(Job)
            .where(
                Job.project_id == project_id,
                Job.status == JobStatus.IN_PROGRESS,
                Job.lease_expires_at < now,
            )
            .values(
                status=JobStatus.UNASSIGNED,
                assignee_id=None,
                lease_expires_at=None,
                draft=None,
                draft_updated_at=None,
            )
        )

    async def release_jobs(
        self,
        now: datetime,
        *,
        user_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        team_id: uuid.UUID | None = None,
    ) -> None:
        """Return open work of a user (or a whole team in a project) to the pools."""
        conds = []
        if project_id:
            conds.append(Job.project_id == project_id)
        if team_id:
            conds.append(Job.task_id.in_(select(Task.id).where(Task.team_id == team_id)))
        annotate = [Job.status.in_(OPEN_ANNOTATOR_STATUSES), *conds]
        review = [Job.status == JobStatus.IN_REVIEW, *conds]
        if user_id:
            annotate.append(Job.assignee_id == user_id)
            review.append(Job.reviewer_id == user_id)
        await self.session.execute(
            update(Job)
            .where(and_(*annotate))
            .values(
                status=JobStatus.UNASSIGNED,
                assignee_id=None,
                lease_expires_at=None,
                draft=None,
                draft_updated_at=None,
            )
        )
        await self.session.execute(
            update(Job).where(and_(*review)).values(status=JobStatus.SUBMITTED, reviewer_id=None)
        )

    # ---------- items in a job ----------

    async def job_items(self, job_id: uuid.UUID) -> list[Item]:
        rows = await self.session.scalars(
            select(Item)
            .join(JobItem, JobItem.item_id == Item.id)
            .where(JobItem.job_id == job_id)
            .order_by(JobItem.position)
        )
        return list(rows)

    # ---------- submissions and reviews ----------

    async def submissions(self, job_id: uuid.UUID) -> list[Submission]:
        rows = await self.session.scalars(
            select(Submission).where(Submission.job_id == job_id).order_by(Submission.round)
        )
        return list(rows)

    async def annotations(self, submission_ids: Sequence[uuid.UUID]) -> list[Annotation]:
        if not submission_ids:
            return []
        rows = await self.session.scalars(
            select(Annotation).where(Annotation.submission_id.in_(submission_ids))
        )
        return list(rows)

    async def reviews(self, job_id: uuid.UUID) -> list[Review]:
        rows = await self.session.scalars(
            select(Review).where(Review.job_id == job_id).order_by(Review.created_at)
        )
        return list(rows)

    async def review_errors(self, review_ids: Sequence[uuid.UUID]) -> list[ReviewError]:
        if not review_ids:
            return []
        rows = await self.session.scalars(
            select(ReviewError).where(ReviewError.review_id.in_(review_ids))
        )
        return list(rows)

    # ---------- progress ----------

    async def closed_jobs(
        self, project_id: uuid.UUID, task_id: uuid.UUID | None
    ) -> list[tuple[datetime | None, datetime | None, int]]:
        """(assigned_at, closed_at, rework_count) of accepted jobs."""
        stmt = select(Job.assigned_at, Job.closed_at, Job.rework_count).where(
            Job.project_id == project_id, Job.closed_at.is_not(None)
        )
        if task_id:
            stmt = stmt.where(Job.task_id == task_id)
        rows = await self.session.execute(stmt)
        return [(a, c, r) for a, c, r in rows.tuples()]

    async def accepted_job_ids(self, task_id: uuid.UUID) -> list[uuid.UUID]:
        rows = await self.session.scalars(
            select(Job.id)
            .where(
                Job.task_id == task_id,
                Job.status.in_((JobStatus.ACCEPTED, JobStatus.ACCEPTED_WITH_FIX)),
            )
            .order_by(Job.ordinal)
        )
        return list(rows)

    async def workload(self, project_id: uuid.UUID) -> list[tuple[uuid.UUID, str, int]]:
        """(user_id, 'annotate' | 'review', open jobs)."""
        annot = await self.session.execute(
            select(Job.assignee_id, func.count())
            .where(
                Job.project_id == project_id,
                Job.status.in_(OPEN_ANNOTATOR_STATUSES),
                Job.assignee_id.is_not(None),
            )
            .group_by(Job.assignee_id)
        )
        review = await self.session.execute(
            select(Job.reviewer_id, func.count())
            .where(
                Job.project_id == project_id,
                Job.status == JobStatus.IN_REVIEW,
                Job.reviewer_id.is_not(None),
            )
            .group_by(Job.reviewer_id)
        )
        rows = [(u, "annotate", c) for u, c in annot.tuples() if u]
        rows += [(u, "review", c) for u, c in review.tuples() if u]
        return rows
