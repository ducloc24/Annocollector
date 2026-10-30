import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import (
    DatasetVersion,
    GuidelineVersion,
    Item,
    Project,
    ProjectMember,
    ProjectTeam,
    ReasonCode,
    Team,
    TeamMember,
)
from app.models.rbac import Role
from app.models.user import User


def _active_team_member(now: datetime):
    return TeamMember.removed_at.is_(None) & (
        TeamMember.expires_at.is_(None) | (TeamMember.expires_at > now)
    )


def _active_member(now: datetime):
    return ProjectMember.revoked_at.is_(None) & (
        ProjectMember.expires_at.is_(None) | (ProjectMember.expires_at > now)
    )


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, obj):
        self.session.add(obj)
        await self.session.flush()
        return obj

    # ---------- projects ----------

    async def get(self, project_id: uuid.UUID) -> Project | None:
        return await self.session.get(Project, project_id)

    async def get_by_code(self, code: str) -> Project | None:
        return await self.session.scalar(select(Project).where(Project.code == code))

    async def project_ids_for_user(self, user_id: uuid.UUID, now: datetime) -> list[uuid.UUID]:
        direct = select(ProjectMember.project_id).where(
            ProjectMember.user_id == user_id, _active_member(now)
        )
        via_team = (
            select(ProjectTeam.project_id)
            .join(TeamMember, TeamMember.team_id == ProjectTeam.team_id)
            .where(
                ProjectTeam.removed_at.is_(None),
                TeamMember.user_id == user_id,
                _active_team_member(now),
            )
        )
        rows = await self.session.scalars(direct.union(via_team))
        return list(rows)

    async def list_projects(self, ids: Sequence[uuid.UUID]) -> list[Project]:
        if not ids:
            return []
        rows = await self.session.scalars(
            select(Project).where(Project.id.in_(ids)).order_by(Project.created_at.desc())
        )
        return list(rows)

    # ---------- direct members ----------

    async def members(
        self, project_id: uuid.UUID, now: datetime
    ) -> list[tuple[ProjectMember, Role, User]]:
        rows = await self.session.execute(
            select(ProjectMember, Role, User)
            .join(Role, Role.id == ProjectMember.role_id)
            .join(User, User.id == ProjectMember.user_id)
            .where(ProjectMember.project_id == project_id, _active_member(now))
            .order_by(Role.code, User.full_name)
        )
        return [(m, r, u) for m, r, u in rows.tuples()]

    async def get_member(self, member_id: uuid.UUID) -> ProjectMember | None:
        return await self.session.get(ProjectMember, member_id)

    async def count_owners(self, project_id: uuid.UUID, now: datetime) -> int:
        total = await self.session.scalar(
            select(func.count())
            .select_from(ProjectMember)
            .join(Role, Role.id == ProjectMember.role_id)
            .where(
                ProjectMember.project_id == project_id,
                Role.code == "owner",
                Role.scope == "project",
                _active_member(now),
            )
        )
        return total or 0

    # ---------- teams ----------

    async def get_team(self, team_id: uuid.UUID) -> Team | None:
        return await self.session.get(Team, team_id)

    async def get_team_by_code(self, code: str) -> Team | None:
        return await self.session.scalar(select(Team).where(Team.code == code))

    async def list_teams(self, q: str | None, status: str | None) -> list[Team]:
        stmt = select(Team)
        if q:
            pattern = f"%{q.lower()}%"
            stmt = stmt.where(
                or_(func.lower(Team.name).like(pattern), func.lower(Team.code).like(pattern))
            )
        if status:
            stmt = stmt.where(Team.status == status)
        return list(await self.session.scalars(stmt.order_by(Team.name)))

    async def team_members(
        self, team_ids: Sequence[uuid.UUID], now: datetime
    ) -> list[tuple[TeamMember, User]]:
        if not team_ids:
            return []
        rows = await self.session.execute(
            select(TeamMember, User)
            .join(User, User.id == TeamMember.user_id)
            .where(TeamMember.team_id.in_(team_ids), _active_team_member(now))
            .order_by(TeamMember.team_role, User.full_name)
        )
        return [(m, u) for m, u in rows.tuples()]

    async def get_team_member(self, member_id: uuid.UUID) -> TeamMember | None:
        return await self.session.get(TeamMember, member_id)

    async def user_team_memberships(
        self, user_id: uuid.UUID, now: datetime
    ) -> list[tuple[TeamMember, Team]]:
        rows = await self.session.execute(
            select(TeamMember, Team)
            .join(Team, Team.id == TeamMember.team_id)
            .where(TeamMember.user_id == user_id, _active_team_member(now))
            .order_by(Team.name)
        )
        return [(m, t) for m, t in rows.tuples()]

    async def project_teams(self, project_id: uuid.UUID) -> list[tuple[ProjectTeam, Team]]:
        rows = await self.session.execute(
            select(ProjectTeam, Team)
            .join(Team, Team.id == ProjectTeam.team_id)
            .where(ProjectTeam.project_id == project_id, ProjectTeam.removed_at.is_(None))
            .order_by(Team.name)
        )
        return [(pt, t) for pt, t in rows.tuples()]

    async def get_project_team(self, link_id: uuid.UUID) -> ProjectTeam | None:
        return await self.session.get(ProjectTeam, link_id)

    async def projects_of_team(self, team_id: uuid.UUID) -> list[uuid.UUID]:
        rows = await self.session.scalars(
            select(ProjectTeam.project_id).where(
                ProjectTeam.team_id == team_id, ProjectTeam.removed_at.is_(None)
            )
        )
        return list(rows)

    async def team_roles_in_project(
        self, project_id: uuid.UUID, now: datetime
    ) -> list[tuple[uuid.UUID, str, uuid.UUID]]:
        """(user_id, team_role, team_id) for every active member of every linked team."""
        rows = await self.session.execute(
            select(TeamMember.user_id, TeamMember.team_role, TeamMember.team_id)
            .join(ProjectTeam, ProjectTeam.team_id == TeamMember.team_id)
            .where(
                ProjectTeam.project_id == project_id,
                ProjectTeam.removed_at.is_(None),
                _active_team_member(now),
            )
        )
        return [(u, r, t) for u, r, t in rows.tuples()]

    # ---------- guidelines ----------

    async def guidelines(self, project_id: uuid.UUID) -> list[GuidelineVersion]:
        rows = await self.session.scalars(
            select(GuidelineVersion)
            .where(GuidelineVersion.project_id == project_id)
            .order_by(GuidelineVersion.version.desc())
        )
        return list(rows)

    async def guideline(self, project_id: uuid.UUID, version: int) -> GuidelineVersion | None:
        return await self.session.scalar(
            select(GuidelineVersion).where(
                GuidelineVersion.project_id == project_id, GuidelineVersion.version == version
            )
        )

    async def next_version(self, model, project_id: uuid.UUID) -> int:
        current = await self.session.scalar(
            select(func.max(model.version)).where(model.project_id == project_id)
        )
        return (current or 0) + 1

    # ---------- reason codes ----------

    async def reason_codes(self, project_id: uuid.UUID) -> list[ReasonCode]:
        rows = await self.session.scalars(
            select(ReasonCode).where(ReasonCode.project_id == project_id).order_by(ReasonCode.code)
        )
        return list(rows)

    async def get_reason_code(self, code_id: uuid.UUID) -> ReasonCode | None:
        return await self.session.get(ReasonCode, code_id)

    # ---------- datasets ----------

    async def datasets(self, project_id: uuid.UUID) -> list[DatasetVersion]:
        rows = await self.session.scalars(
            select(DatasetVersion)
            .where(DatasetVersion.project_id == project_id, DatasetVersion.deleted_at.is_(None))
            .order_by(DatasetVersion.version.desc())
        )
        return list(rows)

    async def dataset(self, project_id: uuid.UUID, version: int) -> DatasetVersion | None:
        return await self.session.scalar(
            select(DatasetVersion).where(
                DatasetVersion.project_id == project_id,
                DatasetVersion.version == version,
                DatasetVersion.deleted_at.is_(None),
            )
        )

    async def items(
        self, dataset_version_id: uuid.UUID, offset: int, limit: int
    ) -> tuple[list[Item], int]:
        total = await self.session.scalar(
            select(func.count()).where(Item.dataset_version_id == dataset_version_id)
        )
        rows = await self.session.scalars(
            select(Item)
            .where(Item.dataset_version_id == dataset_version_id)
            .order_by(Item.ordinal)
            .offset(offset)
            .limit(limit)
        )
        return list(rows), total or 0

    async def all_item_ids(self, dataset_version_id: uuid.UUID) -> list[uuid.UUID]:
        rows = await self.session.scalars(
            select(Item.id)
            .where(Item.dataset_version_id == dataset_version_id)
            .order_by(Item.ordinal)
        )
        return list(rows)

    async def add_items(self, items: list[Item]) -> None:
        self.session.add_all(items)
        await self.session.flush()
