import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ops import Appeal, GoldAnswer, SystemSetting
from app.models.project import Item, TeamMember
from app.models.work import (
    Annotation,
    Job,
    JobItem,
    JobStatus,
    Review,
    ReviewError,
    Submission,
    Task,
)


class OpsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, obj):
        self.session.add(obj)
        await self.session.flush()
        return obj

    # ---------- settings ----------

    async def settings(self) -> dict[str, Any]:
        rows = await self.session.scalars(select(SystemSetting))
        return {row.key: row.value for row in rows}

    async def get_setting(self, key: str) -> SystemSetting | None:
        return await self.session.get(SystemSetting, key)

    # ---------- appeals ----------

    async def get_appeal(self, appeal_id: uuid.UUID) -> Appeal | None:
        return await self.session.get(Appeal, appeal_id)

    async def open_appeal_for_job(self, job_id: uuid.UUID) -> Appeal | None:
        return await self.session.scalar(
            select(Appeal).where(Appeal.job_id == job_id, Appeal.status != "closed")
        )

    async def appeals(
        self, project_id: uuid.UUID, *, status: str | None, opened_by: uuid.UUID | None = None
    ) -> list[Appeal]:
        stmt = select(Appeal).where(Appeal.project_id == project_id)
        if status:
            stmt = stmt.where(Appeal.status == status)
        if opened_by:
            stmt = stmt.where(Appeal.opened_by == opened_by)
        return list(await self.session.scalars(stmt.order_by(Appeal.opened_at.desc())))

    async def appeals_of_user(self, user_id: uuid.UUID) -> list[Appeal]:
        rows = await self.session.scalars(
            select(Appeal).where(Appeal.opened_by == user_id).order_by(Appeal.opened_at.desc())
        )
        return list(rows)

    async def last_review(self, job_id: uuid.UUID, kinds: Sequence[str]) -> Review | None:
        return await self.session.scalar(
            select(Review)
            .where(Review.job_id == job_id, Review.kind.in_(kinds))
            .order_by(Review.created_at.desc())
            .limit(1)
        )

    # ---------- gold ----------

    async def gold_answers(self, project_id: uuid.UUID) -> list[GoldAnswer]:
        rows = await self.session.scalars(
            select(GoldAnswer)
            .join(Job, Job.id == GoldAnswer.job_id)
            .where(Job.project_id == project_id)
        )
        return list(rows)

    async def job_annotations(
        self, job_id: uuid.UUID
    ) -> tuple[Submission | None, list[Annotation]]:
        submission = await self.session.scalar(
            select(Submission)
            .where(Submission.job_id == job_id)
            .order_by(Submission.round.desc())
            .limit(1)
        )
        if submission is None:
            return None, []
        rows = await self.session.scalars(
            select(Annotation).where(Annotation.submission_id == submission.id)
        )
        return submission, list(rows)

    async def next_job_ordinal(self, task_id: uuid.UUID) -> int:
        current = await self.session.scalar(
            select(func.max(Job.ordinal)).where(Job.task_id == task_id)
        )
        return (current or 0) + 1

    async def item_ids_of_job(self, job_id: uuid.UUID) -> list[tuple[uuid.UUID, int]]:
        rows = await self.session.execute(
            select(JobItem.item_id, JobItem.position).where(JobItem.job_id == job_id)
        )
        return [(i, p) for i, p in rows.tuples()]

    # ---------- quality queries ----------

    async def closed_job_rows(
        self, project_id: uuid.UUID | None = None, *, task_ids: Sequence[uuid.UUID] | None = None
    ) -> list[tuple[uuid.UUID, uuid.UUID | None, int, datetime | None, bool]]:
        """(job_id, assignee_id, rework_count, closed_at, is_gold) of accepted jobs."""
        stmt = select(Job.id, Job.assignee_id, Job.rework_count, Job.closed_at, Job.is_gold).where(
            Job.closed_at.is_not(None),
            Job.status.in_((JobStatus.ACCEPTED, JobStatus.ACCEPTED_WITH_FIX)),
        )
        if project_id:
            stmt = stmt.where(Job.project_id == project_id)
        if task_ids is not None:
            stmt = stmt.where(Job.task_id.in_(task_ids))
        rows = await self.session.execute(stmt)
        return [(j, a, r, c, g) for j, a, r, c, g in rows.tuples()]

    async def review_rows(
        self, project_id: uuid.UUID | None = None, *, task_ids: Sequence[uuid.UUID] | None = None
    ) -> list[tuple[uuid.UUID, uuid.UUID | None, uuid.UUID | None, str, str]]:
        """(review_id, reviewer_id, annotator_id, decision, kind) for normal reviews."""
        stmt = (
            select(
                Review.id, Review.reviewer_id, Submission.annotator_id, Review.decision, Review.kind
            )
            .join(Submission, Submission.id == Review.submission_id, isouter=True)
            .join(Job, Job.id == Review.job_id)
        )
        if project_id:
            stmt = stmt.where(Job.project_id == project_id)
        if task_ids is not None:
            stmt = stmt.where(Job.task_id.in_(task_ids))
        rows = await self.session.execute(stmt)
        return [(i, r, a, d, k) for i, r, a, d, k in rows.tuples()]

    async def overridden_review_ids(self, project_id: uuid.UUID) -> set[uuid.UUID]:
        rows = await self.session.scalars(
            select(Review.supersedes_review_id)
            .join(Job, Job.id == Review.job_id)
            .where(
                Job.project_id == project_id,
                Review.kind.in_(("override", "appeal_decision")),
                Review.supersedes_review_id.is_not(None),
            )
        )
        return {r for r in rows if r}

    async def error_rows(
        self, project_id: uuid.UUID | None = None, *, task_ids: Sequence[uuid.UUID] | None = None
    ) -> list[tuple[str, str, uuid.UUID | None]]:
        """(reason_code, severity, annotator_id) of every recorded error."""
        stmt = (
            select(ReviewError.reason_code, ReviewError.severity, Submission.annotator_id)
            .join(Review, Review.id == ReviewError.review_id)
            .join(Submission, Submission.id == Review.submission_id, isouter=True)
            .join(Job, Job.id == Review.job_id)
        )
        if project_id:
            stmt = stmt.where(Job.project_id == project_id)
        if task_ids is not None:
            stmt = stmt.where(Job.task_id.in_(task_ids))
        rows = await self.session.execute(stmt)
        return [(c, s, a) for c, s, a in rows.tuples()]

    async def annotator_rejects(self, project_id: uuid.UUID) -> list[tuple[uuid.UUID, str]]:
        rows = await self.session.execute(
            select(Submission.annotator_id, Review.decision)
            .join(Review, Review.submission_id == Submission.id)
            .join(Job, Job.id == Submission.job_id)
            .where(Job.project_id == project_id, Review.kind == "review")
        )
        return [(a, d) for a, d in rows.tuples()]

    # ---------- team lead ----------

    async def team_tasks(self, team_id: uuid.UUID) -> list[Task]:
        return list(await self.session.scalars(select(Task).where(Task.team_id == team_id)))

    async def lead_membership(self, user_id: uuid.UUID, team_id: uuid.UUID) -> TeamMember | None:
        return await self.session.scalar(
            select(TeamMember).where(
                TeamMember.user_id == user_id,
                TeamMember.team_id == team_id,
                TeamMember.is_lead.is_(True),
                TeamMember.removed_at.is_(None),
            )
        )

    async def open_counts(self, task_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
        """Per user: jobs they hold as annotator or reviewer right now."""
        result: dict[uuid.UUID, dict[str, int]] = {}
        if not task_ids:
            return result
        annotating = await self.session.execute(
            select(Job.assignee_id, func.count())
            .where(
                Job.task_id.in_(task_ids),
                Job.assignee_id.is_not(None),
                Job.status.in_((JobStatus.ASSIGNED, JobStatus.IN_PROGRESS, JobStatus.REJECTED)),
            )
            .group_by(Job.assignee_id)
        )
        for user_id, n in annotating.tuples():
            if user_id is not None:
                result.setdefault(user_id, {})["annotating"] = n
        reviewing = await self.session.execute(
            select(Job.reviewer_id, func.count())
            .where(
                Job.task_id.in_(task_ids),
                Job.reviewer_id.is_not(None),
                Job.status == JobStatus.IN_REVIEW,
            )
            .group_by(Job.reviewer_id)
        )
        for user_id, n in reviewing.tuples():
            if user_id is not None:
                result.setdefault(user_id, {})["reviewing"] = n
        return result

    async def stuck_count(self, task_ids: Sequence[uuid.UUID], before: datetime) -> int:
        if not task_ids:
            return 0
        total = await self.session.scalar(
            select(func.count())
            .select_from(Job)
            .where(
                Job.task_id.in_(task_ids),
                Job.status.in_((JobStatus.SUBMITTED, JobStatus.IN_REVIEW, JobStatus.ESCALATED)),
                Job.submitted_at < before,
            )
        )
        return total or 0

    # ---------- export ----------

    async def export_rows(self, task_id: uuid.UUID) -> list[tuple[Job, Item, Annotation | None]]:
        """Final answers: the latest submission of every accepted, non-gold job."""
        jobs = await self.session.scalars(
            select(Job)
            .where(
                Job.task_id == task_id,
                Job.is_gold.is_(False),
                Job.status.in_((JobStatus.ACCEPTED, JobStatus.ACCEPTED_WITH_FIX)),
            )
            .order_by(Job.ordinal)
        )
        rows: list[tuple[Job, Item, Annotation | None]] = []
        for job in jobs:
            _, annotations = await self.job_annotations(job.id)
            items = await self.session.scalars(
                select(Item)
                .join(JobItem, JobItem.item_id == Item.id)
                .where(JobItem.job_id == job.id)
            )
            for item in items:
                mine = [a for a in annotations if a.item_id == item.id]
                if not mine:
                    rows.append((job, item, None))
                rows.extend((job, item, a) for a in mine)
        return rows

    # ---------- maintenance ----------

    async def release_all_expired_leases(self, now: datetime) -> int:
        result = await self.session.execute(
            update(Job)
            .where(Job.status == JobStatus.IN_PROGRESS, Job.lease_expires_at < now)
            .values(
                status=JobStatus.UNASSIGNED,
                assignee_id=None,
                lease_expires_at=None,
                draft=None,
                draft_updated_at=None,
            )
        )
        return int(getattr(result, "rowcount", 0) or 0)
