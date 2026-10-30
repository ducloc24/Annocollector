import uuid

from app.core.clock import Clock, utcnow
from app.core.exceptions import AppError, ConflictError, InvalidStateError, NotFoundError
from app.models.project import Team, TeamMember, TeamStatus
from app.models.user import User, UserStatus
from app.repositories.project import ProjectRepository
from app.repositories.rbac import RbacRepository
from app.repositories.user import UserRepository
from app.repositories.work import WorkRepository
from app.services.audit import AuditService
from app.services.project import find_role_conflicts

TEAM_ROLES = ("annotator", "reviewer")


class TeamService:
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

    async def get(self, team_id: uuid.UUID) -> Team:
        team = await self.projects.get_team(team_id)
        if team is None:
            raise NotFoundError("Team not found")
        return team

    async def create(self, actor: User, code: str, name: str, description: str | None) -> Team:
        code = code.strip()
        if await self.projects.get_team_by_code(code):
            raise ConflictError("Team code is already used", code="team_code_taken")
        team = await self.projects.add(
            Team(
                id=uuid.uuid4(),
                code=code,
                name=name.strip(),
                description=description,
                status=TeamStatus.ACTIVE,
                created_by=actor.id,
            )
        )
        await self.audit.record(
            actor=actor,
            action="team.create",
            target_type="team",
            target_id=team.id,
            after={"code": code, "name": team.name},
        )
        return team

    async def update(self, actor: User, team_id: uuid.UUID, changes: dict[str, object]) -> Team:
        team = await self.get(team_id)
        if changes.get("status") == TeamStatus.ARCHIVED and await self.projects.projects_of_team(
            team.id
        ):
            raise ConflictError(
                "Unlink the team from its projects before archiving", code="team_in_use"
            )
        before = {k: getattr(team, k) for k in changes}
        for key, value in changes.items():
            setattr(team, key, value)
        await self.audit.record(
            actor=actor,
            action="team.update",
            target_type="team",
            target_id=team.id,
            before=before,
            after=changes,
        )
        return team

    async def _check_conflicts(self, team_id: uuid.UUID, user_id: uuid.UUID, role: str) -> None:
        """Would ``user`` become annotator and reviewer in a project using this team?"""
        now = self.clock()
        for project_id in await self.projects.projects_of_team(team_id):
            rows = [
                r
                for r in await self.projects.team_roles_in_project(project_id, now)
                if not (r[0] == user_id and r[2] == team_id)
            ]
            rows.append((user_id, role, team_id))
            if user_id in find_role_conflicts(rows):
                # HR must not learn which project; say only that a conflict exists.
                raise ConflictError(
                    "This person would be both annotator and reviewer in a project that uses "
                    "this team",
                    code="role_conflict",
                )

    async def add_member(
        self,
        actor: User,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
        team_role: str,
        expires_at,
    ) -> TeamMember:
        team = await self.get(team_id)
        if team.status != TeamStatus.ACTIVE:
            raise InvalidStateError("Team is archived", code="team_archived")
        if team_role not in TEAM_ROLES:
            raise AppError("team_role must be annotator or reviewer", code="invalid_team_role")
        user = await self.users.get(user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise NotFoundError("User not found or not active")
        now = self.clock()
        if team_role not in await self.rbac.active_platform_role_codes(user.id, now):
            raise ConflictError(
                f"User needs platform role {team_role} first",
                code="role_requirement_not_met",
                details={"required_platform_role": team_role},
            )
        if any(m.user_id == user.id for m, _ in await self.projects.team_members([team.id], now)):
            raise ConflictError("User is already in this team", code="already_member")
        await self._check_conflicts(team.id, user.id, team_role)
        member = await self.projects.add(
            TeamMember(
                id=uuid.uuid4(),
                team_id=team.id,
                user_id=user.id,
                team_role=team_role,
                is_lead=False,
                added_by=actor.id,
                added_at=now,
                expires_at=expires_at,
            )
        )
        await self.audit.record(
            actor=actor,
            action="team_member.add",
            target_type="team_member",
            target_id=member.id,
            after={"team": team.code, "user_id": str(user.id), "role": team_role},
        )
        return member

    async def _member(self, team_id: uuid.UUID, member_id: uuid.UUID) -> TeamMember:
        member = await self.projects.get_team_member(member_id)
        if member is None or member.team_id != team_id or member.removed_at is not None:
            raise NotFoundError("Team member not found")
        return member

    async def update_member(
        self, actor: User, team_id: uuid.UUID, member_id: uuid.UUID, changes: dict[str, object]
    ) -> TeamMember:
        member = await self._member(team_id, member_id)
        now = self.clock()
        role = changes.get("team_role")
        if role is not None and role != member.team_role:
            if role not in TEAM_ROLES:
                raise AppError("team_role must be annotator or reviewer", code="invalid_team_role")
            if role not in await self.rbac.active_platform_role_codes(member.user_id, now):
                raise ConflictError(
                    f"User needs platform role {role} first", code="role_requirement_not_met"
                )
            await self._check_conflicts(team_id, member.user_id, str(role))
            # Open work under the old role goes back to the pools.
            await self.work.release_jobs(now, user_id=member.user_id, team_id=team_id)
        if changes.get("is_lead") is True:
            for other, _ in await self.projects.team_members([team_id], now):
                if other.is_lead and other.id != member.id:
                    raise ConflictError("The team already has a lead", code="lead_already_assigned")
        before = {k: getattr(member, k) for k in changes}
        for key, value in changes.items():
            setattr(member, key, value)
        await self.audit.record(
            actor=actor,
            action="team_member.update",
            target_type="team_member",
            target_id=member.id,
            before=before,
            after=changes,
        )
        return member

    async def remove_member(
        self, actor: User, team_id: uuid.UUID, member_id: uuid.UUID, reason: str
    ) -> None:
        member = await self._member(team_id, member_id)
        now = self.clock()
        member.removed_at = now
        member.remove_reason = reason
        member.is_lead = False
        await self.work.release_jobs(now, user_id=member.user_id, team_id=team_id)
        await self.audit.record(
            actor=actor,
            action="team_member.remove",
            target_type="team_member",
            target_id=member.id,
            before={"user_id": str(member.user_id), "role": member.team_role},
            reason=reason,
        )
