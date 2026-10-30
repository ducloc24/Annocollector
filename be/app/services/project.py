import difflib
import uuid
from dataclasses import dataclass

from app.core.clock import Clock, utcnow
from app.core.exceptions import (
    AppError,
    ConflictError,
    ForbiddenError,
    InvalidStateError,
    NotFoundError,
)
from app.core.rbac_catalog import ROLE_REQUIREMENTS, ProjectRole, RoleScope
from app.models.project import (
    GuidelineVersion,
    Project,
    ProjectMember,
    ProjectStatus,
    ProjectTeam,
    ReasonCode,
    Team,
    TeamStatus,
)
from app.models.user import User, UserStatus
from app.repositories.project import ProjectRepository
from app.repositories.rbac import RbacRepository
from app.repositories.user import UserRepository
from app.repositories.work import WorkRepository
from app.services.audit import AuditService

DIRECT_ROLES = (ProjectRole.OWNER, ProjectRole.MANAGER, ProjectRole.VIEWER)

# Seeded for every new project; PO can add, rename or deactivate them.
DEFAULT_REASON_CODES: tuple[tuple[str, str, str, str], ...] = (
    ("WRONG_TOOL", "Chọn sai tool", "major", "label"),
    ("WRONG_ARGS", "Sai giá trị tham số", "major", "label"),
    ("MISSING_ARG", "Thiếu tham số bắt buộc", "major", "label"),
    ("HALLUCINATED_ARG", "Tham số bịa, không có trong ngữ cảnh", "major", "label"),
    ("UNNECESSARY_CALL", "Gọi thừa", "minor", "label"),
    ("WRONG_ORDER", "Sai thứ tự", "major", "label"),
    ("IGNORED_RESULT", "Bỏ qua kết quả trước đó", "major", "label"),
    ("WRONG_VERDICT", "Kết luận đúng/sai không khớp guideline", "major", "review"),
    ("MISSING_REASON", "Thiếu hoặc sai mã lý do", "minor", "review"),
    ("MISSING_LABEL", "Bỏ sót tool call", "critical", "review"),
    ("MISSING_NOTE", "Thiếu ghi chú khi guideline yêu cầu", "minor", "review"),
    ("PII_LEAK", "Đưa dữ liệu nhạy cảm vào ghi chú", "critical", "review"),
)

STATUS_TRANSITIONS = {
    "activate": ({ProjectStatus.DRAFT, ProjectStatus.PAUSED}, ProjectStatus.ACTIVE),
    "pause": ({ProjectStatus.ACTIVE}, ProjectStatus.PAUSED),
    "close": (
        {ProjectStatus.DRAFT, ProjectStatus.ACTIVE, ProjectStatus.PAUSED},
        ProjectStatus.CLOSED,
    ),
}


@dataclass(frozen=True)
class TeamRoleConflict:
    user_id: uuid.UUID
    full_name: str


def find_role_conflicts(rows: list[tuple[uuid.UUID, str, uuid.UUID]]) -> set[uuid.UUID]:
    """Users holding both annotator and reviewer across the given team memberships."""
    roles: dict[uuid.UUID, set[str]] = {}
    for user_id, role, _ in rows:
        roles.setdefault(user_id, set()).add(role)
    return {u for u, r in roles.items() if {"annotator", "reviewer"} <= r}


class ProjectService:
    def __init__(
        self,
        projects: ProjectRepository,
        work: WorkRepository,
        users: UserRepository,
        rbac: RbacRepository,
        audit: AuditService,
        clock: Clock = utcnow,
    ) -> None:
        self.projects = projects
        self.work = work
        self.users = users
        self.rbac = rbac
        self.audit = audit
        self.clock = clock

    async def get(self, project_id: uuid.UUID) -> Project:
        project = await self.projects.get(project_id)
        if project is None:
            raise NotFoundError("Project not found")
        return project

    # ---------- project ----------

    async def create(
        self, actor: User, *, code: str, name: str, description: str | None, classification: str
    ) -> Project:
        code = code.strip()
        if await self.projects.get_by_code(code):
            raise ConflictError("Project code is already used", code="project_code_taken")
        project = await self.projects.add(
            Project(
                id=uuid.uuid4(),
                code=code,
                name=name.strip(),
                description=description,
                status=ProjectStatus.DRAFT,
                data_classification=classification,
                owner_id=actor.id,
            )
        )
        owner_role = await self.rbac.get_role(RoleScope.PROJECT, ProjectRole.OWNER)
        assert owner_role is not None
        now = self.clock()
        await self.projects.add(
            ProjectMember(
                id=uuid.uuid4(),
                project_id=project.id,
                user_id=actor.id,
                role_id=owner_role.id,
                assigned_by=actor.id,
                assigned_at=now,
            )
        )
        for code_, label, severity, applies_to in DEFAULT_REASON_CODES:
            await self.projects.add(
                ReasonCode(
                    id=uuid.uuid4(),
                    project_id=project.id,
                    code=code_,
                    label=label,
                    default_severity=severity,
                    applies_to=applies_to,
                    active=True,
                )
            )
        await self.audit.record(
            actor=actor,
            action="project.create",
            target_type="project",
            target_id=project.id,
            project_id=project.id,
            after={"code": project.code, "name": project.name},
        )
        return project

    async def update(
        self, actor: User, project_id: uuid.UUID, changes: dict[str, object]
    ) -> Project:
        project = await self.get(project_id)
        before = {k: getattr(project, k) for k in changes}
        for key, value in changes.items():
            setattr(project, key, value)
        await self.audit.record(
            actor=actor,
            action="project.update",
            target_type="project",
            target_id=project.id,
            project_id=project.id,
            before=before,
            after=changes,
        )
        return project

    async def change_status(self, actor: User, project_id: uuid.UUID, action: str) -> Project:
        project = await self.get(project_id)
        allowed, target = STATUS_TRANSITIONS[action]
        if project.status not in allowed:
            raise InvalidStateError(
                f"Cannot {action} a project in status {project.status}",
                details={"from": project.status, "to": target},
            )
        before = project.status
        project.status = target
        await self.audit.record(
            actor=actor,
            action=f"project.{action}",
            target_type="project",
            target_id=project.id,
            project_id=project.id,
            before={"status": before},
            after={"status": target},
        )
        return project

    # ---------- direct members ----------

    async def add_member(
        self,
        actor: User,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        role_code: str,
        expires_at,
        actor_roles: set[str],
    ) -> ProjectMember:
        await self.get(project_id)
        if role_code not in DIRECT_ROLES:
            raise AppError(
                "Only owner, manager and viewer are added directly; annotators and reviewers "
                "join through a team",
                code="role_not_direct",
            )
        if role_code == ProjectRole.OWNER and ProjectRole.OWNER not in actor_roles:
            raise ForbiddenError("Only an owner can add another owner")
        user = await self.users.get(user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise NotFoundError("User not found or not active")
        now = self.clock()
        required = ROLE_REQUIREMENTS.get(ProjectRole(role_code))
        if required and required not in await self.rbac.active_platform_role_codes(user.id, now):
            raise ConflictError(
                f"User needs platform role {required} first",
                code="role_requirement_not_met",
                details={"required_platform_role": str(required)},
            )
        role = await self.rbac.get_role(RoleScope.PROJECT, role_code)
        assert role is not None
        for member, r, _ in await self.projects.members(project_id, now):
            if member.user_id == user.id and r.code == role_code:
                raise ConflictError("User already has this role", code="role_already_granted")
        member = await self.projects.add(
            ProjectMember(
                id=uuid.uuid4(),
                project_id=project_id,
                user_id=user.id,
                role_id=role.id,
                assigned_by=actor.id,
                assigned_at=now,
                expires_at=expires_at,
            )
        )
        await self.audit.record(
            actor=actor,
            action="project_member.add",
            target_type="project_member",
            target_id=member.id,
            project_id=project_id,
            after={"user_id": str(user.id), "role": role_code},
        )
        return member

    async def remove_member(self, actor: User, project_id: uuid.UUID, member_id: uuid.UUID) -> None:
        member = await self.projects.get_member(member_id)
        if member is None or member.project_id != project_id or member.revoked_at is not None:
            raise NotFoundError("Member not found")
        now = self.clock()
        role = next(
            (r for m, r, _ in await self.projects.members(project_id, now) if m.id == member_id),
            None,
        )
        if (
            role
            and role.code == ProjectRole.OWNER
            and await self.projects.count_owners(project_id, now) <= 1
        ):
            raise ConflictError("A project needs at least one owner", code="last_owner")
        member.revoked_at = now
        await self.audit.record(
            actor=actor,
            action="project_member.remove",
            target_type="project_member",
            target_id=member.id,
            project_id=project_id,
            before={"user_id": str(member.user_id), "role": role.code if role else None},
        )

    # ---------- teams on the project ----------

    async def link_team(
        self, actor: User, project_id: uuid.UUID, team_id: uuid.UUID
    ) -> tuple[ProjectTeam, list[str]]:
        project = await self.get(project_id)
        team = await self.projects.get_team(team_id)
        if team is None or team.status != TeamStatus.ACTIVE:
            raise NotFoundError("Team not found or archived")
        linked = await self.projects.project_teams(project.id)
        if any(t.id == team.id for _, t in linked):
            raise ConflictError("Team is already linked", code="team_already_linked")
        now = self.clock()
        members = await self.projects.team_members([team.id], now)
        team_roles = {m.team_role for m, _ in members}
        if not {"annotator", "reviewer"} <= team_roles:
            raise ConflictError(
                "A team needs at least one annotator and one reviewer",
                code="team_missing_role",
                details={"has": sorted(team_roles)},
            )
        rows = await self.projects.team_roles_in_project(project.id, now)
        rows += [(m.user_id, m.team_role, team.id) for m, _ in members]
        conflicts = find_role_conflicts(rows)
        if conflicts:
            names = {u.id: u.full_name for _, u in members}
            raise ConflictError(
                "Some people would be both annotator and reviewer in this project",
                code="role_conflict",
                details={"users": [{"id": str(u), "full_name": names.get(u)} for u in conflicts]},
            )
        link = await self.projects.add(
            ProjectTeam(
                id=uuid.uuid4(),
                project_id=project.id,
                team_id=team.id,
                assigned_by=actor.id,
                assigned_at=now,
            )
        )
        await self.audit.record(
            actor=actor,
            action="project_team.link",
            target_type="project_team",
            target_id=link.id,
            project_id=project.id,
            after={"team_id": str(team.id), "team": team.code},
        )
        annotators = sum(1 for m, _ in members if m.team_role == "annotator")
        reviewers = len(members) - annotators
        warnings = []
        if reviewers * 10 < annotators:
            warnings.append("Tỷ lệ reviewer thấp so với số annotator; hàng đợi chấm có thể bị tắc")
        return link, warnings

    async def unlink_team(self, actor: User, project_id: uuid.UUID, link_id: uuid.UUID) -> None:
        link = await self.projects.get_project_team(link_id)
        if link is None or link.project_id != project_id or link.removed_at is not None:
            raise NotFoundError("Team link not found")
        if await self.work.team_has_open_tasks(project_id, link.team_id):
            raise ConflictError(
                "The team still has active tasks; give them to another team first",
                code="team_has_active_tasks",
            )
        now = self.clock()
        link.removed_at = now
        await self.work.release_jobs(now, project_id=project_id, team_id=link.team_id)
        await self.audit.record(
            actor=actor,
            action="project_team.unlink",
            target_type="project_team",
            target_id=link.id,
            project_id=project_id,
            before={"team_id": str(link.team_id)},
        )

    async def teams_with_counts(
        self, project_id: uuid.UUID
    ) -> list[tuple[ProjectTeam, Team, int, int]]:
        linked = await self.projects.project_teams(project_id)
        members = await self.projects.team_members([t.id for _, t in linked], self.clock())
        result = []
        for link, team in linked:
            roles = [m.team_role for m, _ in members if m.team_id == team.id]
            result.append((link, team, roles.count("annotator"), roles.count("reviewer")))
        return result

    # ---------- guidelines ----------

    async def add_guideline(
        self, actor: User, project_id: uuid.UUID, content: str
    ) -> GuidelineVersion:
        await self.get(project_id)
        version = await self.projects.next_version(GuidelineVersion, project_id)
        guideline = await self.projects.add(
            GuidelineVersion(
                id=uuid.uuid4(),
                project_id=project_id,
                version=version,
                content=content,
                created_by=actor.id,
            )
        )
        await self.audit.record(
            actor=actor,
            action="guideline.create",
            target_type="guideline_version",
            target_id=guideline.id,
            project_id=project_id,
            after={"version": version},
        )
        return guideline

    async def guideline(self, project_id: uuid.UUID, version: int) -> GuidelineVersion:
        guideline = await self.projects.guideline(project_id, version)
        if guideline is None:
            raise NotFoundError("Guideline version not found")
        return guideline

    async def guideline_diff(self, project_id: uuid.UUID, version: int, base: int) -> str:
        new = await self.guideline(project_id, version)
        old = await self.guideline(project_id, base)
        return "\n".join(
            difflib.unified_diff(
                old.content.splitlines(),
                new.content.splitlines(),
                fromfile=f"v{base}",
                tofile=f"v{version}",
                lineterm="",
            )
        )

    # ---------- reason codes ----------

    async def add_reason_code(
        self,
        actor: User,
        project_id: uuid.UUID,
        code: str,
        label: str,
        severity: str,
        applies_to: str,
    ) -> ReasonCode:
        code = code.strip().upper()
        if any(rc.code == code for rc in await self.projects.reason_codes(project_id)):
            raise ConflictError("Reason code already exists", code="reason_code_taken")
        rc = await self.projects.add(
            ReasonCode(
                id=uuid.uuid4(),
                project_id=project_id,
                code=code,
                label=label,
                default_severity=severity,
                applies_to=applies_to,
                active=True,
            )
        )
        await self.audit.record(
            actor=actor,
            action="reason_code.create",
            target_type="reason_code",
            target_id=rc.id,
            project_id=project_id,
            after={"code": code},
        )
        return rc

    async def update_reason_code(
        self, actor: User, project_id: uuid.UUID, code_id: uuid.UUID, changes: dict[str, object]
    ) -> ReasonCode:
        rc = await self.projects.get_reason_code(code_id)
        if rc is None or rc.project_id != project_id:
            raise NotFoundError("Reason code not found")
        for key, value in changes.items():
            setattr(rc, key, value)
        await self.audit.record(
            actor=actor,
            action="reason_code.update",
            target_type="reason_code",
            target_id=rc.id,
            project_id=project_id,
            after=changes,
        )
        return rc
