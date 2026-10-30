import uuid
from typing import Any

from app.core.clock import Clock, utcnow
from app.core.exceptions import AppError, ConflictError, InvalidStateError, NotFoundError
from app.domain import label_schema
from app.domain.item_types import get_item_type
from app.domain.job_rules import normalize_rules, validate_self_check
from app.models.project import ProjectStatus
from app.models.user import User
from app.models.work import Job, JobConfig, JobItem, JobStatus, Task, TaskStatus
from app.repositories.project import ProjectRepository
from app.repositories.work import WorkRepository
from app.services.audit import AuditService


def check_job_config(
    item_type: str, schema: Any, rules: Any, self_check: Any
) -> tuple[dict[str, Any], list[str]]:
    """Validate a job config draft; return (normalized rules, problems)."""
    errors: list[str] = []
    if get_item_type(item_type) is None:
        errors.append(f"Unknown item_type {item_type}")
    errors += label_schema.validate_schema(schema)
    normalized, rule_errors = normalize_rules(rules)
    errors += rule_errors
    errors += validate_self_check(self_check)
    return normalized, errors


def split_into_jobs(item_ids: list[uuid.UUID], per_job: int) -> list[list[uuid.UUID]]:
    return [item_ids[i : i + per_job] for i in range(0, len(item_ids), per_job)]


class TaskService:
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

    # ---------- job configs ----------

    async def create_config(
        self,
        actor: User,
        project_id: uuid.UUID,
        item_type: str,
        schema: Any,
        rules: Any,
        self_check: Any,
    ) -> JobConfig:
        normalized, errors = check_job_config(item_type, schema, rules, self_check)
        if errors:
            raise AppError(
                "Job config is invalid", code="label_schema_invalid", details={"errors": errors}
            )
        version = await self.projects.next_version(JobConfig, project_id)
        config = await self.work.add(
            JobConfig(
                id=uuid.uuid4(),
                project_id=project_id,
                version=version,
                item_type=item_type,
                label_schema=schema,
                job_rules=normalized,
                self_check=self_check,
                created_by=actor.id,
            )
        )
        await self.audit.record(
            actor=actor,
            action="job_config.create",
            target_type="job_config",
            target_id=config.id,
            project_id=project_id,
            after={"version": version, "item_type": item_type},
        )
        return config

    async def config(self, project_id: uuid.UUID, version: int) -> JobConfig:
        config = await self.work.job_config(project_id, version)
        if config is None:
            raise NotFoundError("Job config version not found")
        return config

    # ---------- tasks ----------

    async def get(self, project_id: uuid.UUID, task_id: uuid.UUID) -> Task:
        task = await self.work.get_task(task_id)
        if task is None or task.project_id != project_id:
            raise NotFoundError("Task not found")
        return task

    async def _check_team(self, project_id: uuid.UUID, team_id: uuid.UUID) -> None:
        linked = {t.id for _, t in await self.projects.project_teams(project_id)}
        if team_id not in linked:
            raise ConflictError(
                "The team is not linked to this project", code="team_not_in_project"
            )

    async def create(
        self,
        actor: User,
        project_id: uuid.UUID,
        *,
        name: str,
        dataset_version: int,
        job_config_version: int,
        guideline_version: int,
        team_id: uuid.UUID | None,
        priority: int,
    ) -> tuple[Task, int]:
        dataset = await self.projects.dataset(project_id, dataset_version)
        if dataset is None:
            raise NotFoundError("Dataset version not found")
        config = await self.config(project_id, job_config_version)
        guideline = await self.projects.guideline(project_id, guideline_version)
        if guideline is None:
            raise NotFoundError("Guideline version not found")
        if dataset.item_type != config.item_type:
            raise ConflictError(
                "Dataset and job config are for different item types",
                code="item_type_mismatch",
                details={"dataset": dataset.item_type, "job_config": config.item_type},
            )
        if team_id:
            await self._check_team(project_id, team_id)
        task = await self.work.add(
            Task(
                id=uuid.uuid4(),
                project_id=project_id,
                name=name.strip(),
                dataset_version_id=dataset.id,
                job_config_id=config.id,
                guideline_version_id=guideline.id,
                team_id=team_id,
                priority=priority,
                status=TaskStatus.DRAFT,
                created_by=actor.id,
            )
        )
        groups = split_into_jobs(
            await self.projects.all_item_ids(dataset.id), int(config.job_rules["items_per_job"])
        )
        jobs, links = [], []
        for ordinal, group in enumerate(groups, start=1):
            job = Job(
                id=uuid.uuid4(),
                project_id=project_id,
                task_id=task.id,
                guideline_version_id=guideline.id,
                job_config_id=config.id,
                ordinal=ordinal,
                status=JobStatus.UNASSIGNED,
                rework_count=0,
                has_unsure=False,
                is_gold=False,
            )
            jobs.append(job)
            links += [
                JobItem(job_id=job.id, item_id=item_id, position=pos)
                for pos, item_id in enumerate(group, start=1)
            ]
        await self.work.add_all(jobs)
        await self.work.add_all(links)
        await self.audit.record(
            actor=actor,
            action="task.create",
            target_type="task",
            target_id=task.id,
            project_id=project_id,
            after={"name": task.name, "jobs": len(jobs)},
        )
        return task, len(jobs)

    async def set_team(
        self, actor: User, project_id: uuid.UUID, task_id: uuid.UUID, team_id: uuid.UUID
    ) -> Task:
        task = await self.get(project_id, task_id)
        if task.status == TaskStatus.DELIVERED:
            raise InvalidStateError("Task is delivered", code="task_delivered")
        await self._check_team(project_id, team_id)
        before = task.team_id
        if before and before != team_id:
            # Work not started yet goes back to the pool for the new team.
            await self.work.release_jobs(self.clock(), project_id=project_id, team_id=before)
        task.team_id = team_id
        await self.audit.record(
            actor=actor,
            action="task.set_team",
            target_type="task",
            target_id=task.id,
            project_id=project_id,
            before={"team_id": str(before) if before else None},
            after={"team_id": str(team_id)},
        )
        return task

    async def update(
        self, actor: User, project_id: uuid.UUID, task_id: uuid.UUID, changes: dict[str, object]
    ) -> Task:
        task = await self.get(project_id, task_id)
        for key, value in changes.items():
            setattr(task, key, value)
        await self.audit.record(
            actor=actor,
            action="task.update",
            target_type="task",
            target_id=task.id,
            project_id=project_id,
            after=changes,
        )
        return task

    async def activate(self, actor: User, project_id: uuid.UUID, task_id: uuid.UUID) -> Task:
        task = await self.get(project_id, task_id)
        if task.status != TaskStatus.DRAFT:
            raise InvalidStateError("Only a draft task can be activated", code="invalid_state")
        if task.team_id is None:
            raise ConflictError("Give the task to a team first", code="task_has_no_team")
        project = await self.projects.get(project_id)
        if project is None or project.status != ProjectStatus.ACTIVE:
            raise ConflictError("Activate the project first", code="project_not_active")
        members = await self.projects.team_members([task.team_id], self.clock())
        roles = {m.team_role for m, _ in members}
        if not {"annotator", "reviewer"} <= roles:
            raise ConflictError(
                "The team needs at least one annotator and one reviewer",
                code="team_missing_role",
                details={"has": sorted(roles)},
            )
        task.status = TaskStatus.ACTIVE
        await self.audit.record(
            actor=actor,
            action="task.activate",
            target_type="task",
            target_id=task.id,
            project_id=project_id,
        )
        return task
