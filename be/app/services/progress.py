import math
import random
import uuid
from datetime import datetime, timedelta
from typing import Any

from app.core.clock import Clock, utcnow
from app.core.exceptions import ConflictError, InvalidStateError
from app.models.user import User
from app.models.work import CLOSED_JOB_STATUSES, JobStatus, Task, TaskStatus
from app.repositories.work import WorkRepository
from app.services.audit import AuditService

THROUGHPUT_DAYS = 7
STUCK_HOURS = 24
SAMPLE_RATE = 0.05
SAMPLE_MAX = 20


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(p * len(ordered)) - 1))
    return round(ordered[index], 1)


def summarize(
    counts: dict[str, int],
    closed: list[tuple[datetime | None, datetime | None, int]],
    now: datetime,
) -> dict[str, Any]:
    total = sum(counts.values())
    done = sum(counts.get(s, 0) for s in CLOSED_JOB_STATUSES)
    hours = [
        (c - a).total_seconds() / 3600 for a, c, _ in closed if a is not None and c is not None
    ]
    recent = [
        c for _, c, _ in closed if c is not None and c >= now - timedelta(days=THROUGHPUT_DAYS)
    ]
    first_pass = sum(1 for _, _, rework in closed if rework == 0)
    return {
        "jobs_total": total,
        "by_status": {s.value: counts.get(s.value, 0) for s in JobStatus},
        "completion_rate": round(done / total, 3) if total else 0.0,
        "backlog": counts.get(JobStatus.UNASSIGNED, 0)
        + counts.get(JobStatus.SUBMITTED, 0)
        + counts.get(JobStatus.IN_REVIEW, 0),
        "throughput_per_day": round(len(recent) / THROUGHPUT_DAYS, 1),
        "cycle_time_hours": {"p50": percentile(hours, 0.5), "p90": percentile(hours, 0.9)},
        "first_pass_rate": round(first_pass / len(closed), 3) if closed else None,
        "as_of": now.isoformat(),
    }


def acceptance_sample(task_id: uuid.UUID, job_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """Fixed random sample per task so reopening the page shows the same jobs."""
    if not job_ids:
        return []
    size = min(SAMPLE_MAX, max(1, math.ceil(len(job_ids) * SAMPLE_RATE)))
    return sorted(random.Random(task_id.int).sample(job_ids, size), key=job_ids.index)


class ProgressService:
    def __init__(self, work: WorkRepository, audit: AuditService, clock: Clock = utcnow) -> None:
        self.work = work
        self.audit = audit
        self.clock = clock

    async def progress(self, project_id: uuid.UUID, task_id: uuid.UUID | None) -> dict[str, Any]:
        now = self.clock()
        counts = await self.work.status_counts(project_id, task_id)
        closed = await self.work.closed_jobs(project_id, task_id)
        summary = summarize(counts, closed, now)
        _, stuck = await self.work.list_jobs(
            project_id,
            status=None,
            task_id=task_id,
            assignee_id=None,
            reviewer_id=None,
            stuck_before=now - timedelta(hours=STUCK_HOURS),
            offset=0,
            limit=1,
        )
        summary["stuck"] = stuck
        return summary

    async def acceptance(self, task: Task) -> dict[str, Any]:
        counts = await self.work.status_counts(task.project_id, task.id)
        closed = await self.work.closed_jobs(task.project_id, task.id)
        summary = summarize(counts, closed, self.clock())
        accepted = await self.work.accepted_job_ids(task.id)
        open_jobs = summary["jobs_total"] - sum(counts.get(s, 0) for s in CLOSED_JOB_STATUSES)
        return {
            **summary,
            "task_status": task.status,
            "open_jobs": open_jobs,
            "can_sign_off": task.status == TaskStatus.ACTIVE
            and open_jobs == 0
            and summary["jobs_total"] > 0,
            "sample_job_ids": [str(j) for j in acceptance_sample(task.id, accepted)],
        }

    async def sign_off(self, actor: User, task: Task) -> Task:
        if task.status != TaskStatus.ACTIVE:
            raise InvalidStateError("Only an active task can be signed off")
        counts = await self.work.status_counts(task.project_id, task.id)
        open_jobs = sum(c for s, c in counts.items() if s not in CLOSED_JOB_STATUSES)
        if open_jobs:
            raise ConflictError(
                "Some jobs are not finished",
                code="task_not_complete",
                details={"open_jobs": open_jobs},
            )
        task.status = TaskStatus.DELIVERED
        task.signed_off_by = actor.id
        task.delivered_at = self.clock()
        await self.audit.record(
            actor=actor,
            action="task.sign_off",
            target_type="task",
            target_id=task.id,
            project_id=task.project_id,
        )
        return task
