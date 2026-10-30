import json
import uuid
from collections import defaultdict
from datetime import timedelta
from typing import Any

from app.core.clock import Clock, utcnow
from app.core.exceptions import ConflictError, InvalidStateError, NotFoundError
from app.domain import quality as q
from app.models.ops import GoldAnswer
from app.models.user import User
from app.models.work import Job, JobItem, JobStatus, Task, TaskStatus
from app.repositories.ops import OpsRepository
from app.repositories.project import ProjectRepository
from app.repositories.work import WorkRepository
from app.services.audit import AuditService
from app.services.settings import SettingsService

Key = tuple[str, str | None]


class QualityService:
    def __init__(
        self,
        ops: OpsRepository,
        projects: ProjectRepository,
        work: WorkRepository,
        settings: SettingsService,
        audit: AuditService,
        clock: Clock = utcnow,
    ) -> None:
        self.ops = ops
        self.projects = projects
        self.work = work
        self.settings = settings
        self.audit = audit
        self.clock = clock

    # ---------- gold jobs ----------

    async def make_gold(self, actor: User, project_id: uuid.UUID, source_job_id: uuid.UUID) -> Job:
        """Clone an accepted job as a gold job; its accepted labels become the expected answer."""
        source = await self.work.get_job(source_job_id)
        if source is None or source.project_id != project_id:
            raise NotFoundError("Job not found")
        if source.status not in (JobStatus.ACCEPTED, JobStatus.ACCEPTED_WITH_FIX):
            raise InvalidStateError(
                "Only an accepted job can become a gold job", code="not_accepted"
            )
        _, annotations = await self.ops.job_annotations(source.id)
        if not annotations:
            raise ConflictError("The job has no accepted labels", code="no_labels")
        gold = await self.work.add(
            Job(
                id=uuid.uuid4(),
                project_id=project_id,
                task_id=source.task_id,
                guideline_version_id=source.guideline_version_id,
                job_config_id=source.job_config_id,
                ordinal=await self.ops.next_job_ordinal(source.task_id),
                status=JobStatus.UNASSIGNED,
                rework_count=0,
                has_unsure=False,
                is_gold=True,
            )
        )
        await self.work.add_all(
            [
                JobItem(job_id=gold.id, item_id=i, position=p)
                for i, p in await self.ops.item_ids_of_job(source.id)
            ]
        )
        await self.work.add_all(
            [
                GoldAnswer(
                    id=uuid.uuid4(),
                    job_id=gold.id,
                    item_id=a.item_id,
                    target=a.target,
                    expected=a.value,
                )
                for a in annotations
            ]
        )
        await self.audit.record(
            actor=actor,
            action="job.make_gold",
            target_type="job",
            target_id=gold.id,
            project_id=project_id,
            after={"source_job_id": str(source.id)},
        )
        return gold

    # ---------- shared pieces ----------

    async def _gold_by_annotator(self, project_id: uuid.UUID) -> dict[uuid.UUID, tuple[int, int]]:
        answers = await self.ops.gold_answers(project_id)
        by_job: dict[uuid.UUID, dict[Key, Any]] = defaultdict(dict)
        for a in answers:
            by_job[a.job_id][(str(a.item_id), a.target)] = a.expected
        result: dict[uuid.UUID, tuple[int, int]] = {}
        for job_id, expected in by_job.items():
            for submission in await self.work.submissions(job_id):
                given = {
                    (str(a.item_id), a.target): a.value
                    for a in await self.work.annotations([submission.id])
                }
                correct, total = q.gold_accuracy(expected, given)
                c, t = result.get(submission.annotator_id, (0, 0))
                result[submission.annotator_id] = (c + correct, t + total)
        return result

    async def _names(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        from app.models.user import User as UserModel

        names: dict[uuid.UUID, str] = {}
        for uid in ids:
            user = await self.projects.session.get(UserModel, uid)
            if user:
                names[uid] = user.full_name
        return names

    # ---------- project report ----------

    async def project_report(self, project_id: uuid.UUID) -> dict[str, Any]:
        closed = await self.ops.closed_job_rows(project_id)
        real = [(j, a, r, c) for j, a, r, c, gold in closed if not gold]
        reviews = await self.ops.review_rows(project_id)
        overridden = await self.ops.overridden_review_ids(project_id)
        errors = await self.ops.error_rows(project_id)
        gold = await self._gold_by_annotator(project_id)

        annotators: dict[uuid.UUID, q.AnnotatorFacts] = {}
        for _, annotator, rework, _ in real:
            if annotator is None:
                continue
            facts = annotators.setdefault(annotator, q.AnnotatorFacts(user_id=annotator))
            facts.closed += 1
            facts.first_pass += 1 if rework == 0 else 0
            facts.rework_total += rework
        for _, _, annotator, decision, kind in reviews:
            if annotator is None or kind != "review":
                continue
            facts = annotators.setdefault(annotator, q.AnnotatorFacts(user_id=annotator))
            facts.reviews += 1
            facts.rejected_reviews += 1 if decision == "reject" else 0
        for annotator, (correct, total) in gold.items():
            facts = annotators.setdefault(annotator, q.AnnotatorFacts(user_id=annotator))
            facts.gold_correct, facts.gold_total = correct, total

        reviewers: dict[uuid.UUID, dict[str, int]] = {}
        for review_id, reviewer, _, decision, kind in reviews:
            if reviewer is None or kind != "review":
                continue
            row = reviewers.setdefault(reviewer, {"reviews": 0, "rejects": 0, "overridden": 0})
            row["reviews"] += 1
            row["rejects"] += 1 if decision == "reject" else 0
            row["overridden"] += 1 if review_id in overridden else 0

        names = await self._names(set(annotators) | set(reviewers))
        total_reviews = sum(1 for r in reviews if r[4] == "review")
        rejects = sum(1 for r in reviews if r[4] == "review" and r[3] == "reject")
        return {
            "jobs_closed": len(real),
            "first_pass_rate": q.ratio(sum(1 for _, _, rw, _ in real if rw == 0), len(real)),
            "reject_rate": q.ratio(rejects, total_reviews),
            "reason_codes": q.top_reason_codes([(c, s) for c, s, _ in errors]),
            "trend": q.weekly_trend([(c, rw) for _, _, rw, c in real if c is not None]),
            "annotators": [
                {**row, "name": names.get(uuid.UUID(row["user_id"]), "?")}
                for row in q.annotator_stats(annotators.values())
            ],
            "reviewers": [
                {
                    "user_id": str(u),
                    "name": names.get(u, "?"),
                    "reviews": v["reviews"],
                    "reject_rate": q.ratio(v["rejects"], v["reviews"]),
                    "overridden": v["overridden"],
                }
                for u, v in reviewers.items()
            ],
        }

    async def my_report(self, user: User, project_ids: list[uuid.UUID]) -> list[dict[str, Any]]:
        """Own numbers per project, for annotators and reviewers."""
        result = []
        for project_id in project_ids:
            report = await self.project_report(project_id)
            mine_a = next((a for a in report["annotators"] if a["user_id"] == str(user.id)), None)
            mine_r = next((r for r in report["reviewers"] if r["user_id"] == str(user.id)), None)
            if mine_a or mine_r:
                project = await self.projects.get(project_id)
                result.append(
                    {
                        "project": {"id": str(project_id), "name": project.name if project else ""},
                        "as_annotator": mine_a,
                        "as_reviewer": mine_r,
                    }
                )
        return result

    # ---------- team lead ----------

    async def _team_scope(self, user: User, team_id: uuid.UUID) -> tuple[list[Task], list[Any]]:
        if await self.ops.lead_membership(user.id, team_id) is None:
            raise NotFoundError("Team not found")
        tasks = await self.ops.team_tasks(team_id)
        members = await self.projects.team_members([team_id], self.clock())
        return tasks, members

    async def team_overview(self, user: User, team_id: uuid.UUID) -> list[dict[str, Any]]:
        tasks, members = await self._team_scope(user, team_id)
        task_ids = [t.id for t in tasks]
        open_now = await self.ops.open_counts(task_ids)
        closed = await self.ops.closed_job_rows(task_ids=task_ids)
        done_by: dict[uuid.UUID, int] = defaultdict(int)
        for _, assignee, _, _, gold in closed:
            if assignee and not gold:
                done_by[assignee] += 1
        return [
            {
                "user": {"id": str(u.id), "full_name": u.full_name},
                "team_role": m.team_role,
                "is_lead": m.is_lead,
                "annotating": open_now.get(u.id, {}).get("annotating", 0),
                "reviewing": open_now.get(u.id, {}).get("reviewing", 0),
                "jobs_accepted": done_by.get(u.id, 0),
            }
            for m, u in members
        ]

    async def team_quality(self, user: User, team_id: uuid.UUID) -> dict[str, Any]:
        tasks, members = await self._team_scope(user, team_id)
        task_ids = [t.id for t in tasks]
        project_ids = {t.project_id for t in tasks}
        closed = await self.ops.closed_job_rows(task_ids=task_ids)
        errors = await self.ops.error_rows(task_ids=task_ids)
        reviews = await self.ops.review_rows(task_ids=task_ids)
        flagged = defaultdict(set)
        for code, _, annotator in errors:
            if annotator:
                flagged[annotator].add(code)
        rejected_for: dict[tuple[uuid.UUID, str], int] = defaultdict(int)
        # A user rejected twice for the same reason code is flagged for coaching.
        facts: dict[uuid.UUID, q.AnnotatorFacts] = {}
        for _, assignee, rework, _, gold in closed:
            if assignee and not gold:
                f = facts.setdefault(assignee, q.AnnotatorFacts(user_id=assignee))
                f.closed += 1
                f.first_pass += 1 if rework == 0 else 0
                f.rework_total += rework
        for _, _, annotator, decision, kind in reviews:
            if annotator and kind == "review":
                f = facts.setdefault(annotator, q.AnnotatorFacts(user_id=annotator))
                f.reviews += 1
                f.rejected_reviews += 1 if decision == "reject" else 0
        per_user_errors: dict[uuid.UUID, list[tuple[str, str]]] = defaultdict(list)
        for code, sev, annotator in errors:
            if annotator:
                per_user_errors[annotator].append((code, sev))
                rejected_for[(annotator, code)] += 1
        rows = []
        for m, u in members:
            if m.team_role != "annotator":
                continue
            stats = q.annotator_stats([facts.get(u.id) or q.AnnotatorFacts(user_id=u.id)])[0]
            stats.pop("gold_accuracy", None)  # the lead keeps taking part in gold checks blind
            rows.append(
                {
                    **stats,
                    "name": u.full_name,
                    "top_errors": q.top_reason_codes(per_user_errors.get(u.id, []), 3),
                    "coaching_flag": any(
                        n >= 2 for (uid, _), n in rejected_for.items() if uid == u.id
                    ),
                }
            )
        return {
            "members": rows,
            "trend": q.weekly_trend(
                [(c, rw) for _, _, rw, c, gold in closed if not gold and c is not None]
            ),
            "projects": len(project_ids),
        }

    async def team_alerts(self, user: User, team_id: uuid.UUID) -> list[dict[str, str]]:
        tasks, members = await self._team_scope(user, team_id)
        alerts: list[dict[str, str]] = []
        roles = {m.team_role for m, _ in members}
        active = [t for t in tasks if t.status == TaskStatus.ACTIVE]
        for needed in ("annotator", "reviewer"):
            if needed not in roles and active:
                alerts.append(
                    {"level": "red", "text": f"Đội đang có task chạy nhưng thiếu {needed}."}
                )
        annotators = sum(1 for m, _ in members if m.team_role == "annotator")
        reviewers = len(members) - annotators
        if reviewers and annotators / reviewers > 10:
            alerts.append(
                {
                    "level": "amber",
                    "text": "Quá ít reviewer so với annotator; hàng đợi chấm có thể tắc.",
                }
            )
        hours = await self.settings.get("stuck_hours")
        stuck = await self.ops.stuck_count(
            [t.id for t in tasks], self.clock() - timedelta(hours=hours)
        )
        if stuck:
            alerts.append({"level": "amber", "text": f"{stuck} job kẹt quá {hours} giờ."})
        return alerts

    # ---------- export ----------

    async def export_task(self, actor: User, project_id: uuid.UUID, task_id: uuid.UUID) -> str:
        task = await self.work.get_task(task_id)
        if task is None or task.project_id != project_id:
            raise NotFoundError("Task not found")
        if task.status != TaskStatus.DELIVERED:
            raise ConflictError("Only a delivered task can be exported", code="task_not_delivered")
        lines = []
        for job, item, annotation in await self.ops.export_rows(task.id):
            lines.append(
                json.dumps(
                    {
                        "task": task.name,
                        "job": job.ordinal,
                        "item_id": str(item.id),
                        "external_ref": item.external_ref,
                        "item": item.payload,
                        "target": annotation.target if annotation else None,
                        "label": annotation.value if annotation else None,
                        "decision": job.status,
                    },
                    ensure_ascii=False,
                )
            )
        await self.audit.record(
            actor=actor,
            action="task.export",
            target_type="task",
            target_id=task.id,
            project_id=project_id,
            after={"lines": len(lines)},
        )
        return "\n".join(lines) + ("\n" if lines else "")
