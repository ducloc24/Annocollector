"""Import every model here so Alembic autogenerate can see the metadata."""

from app.db.base import Base
from app.models.audit import AuditEvent
from app.models.ops import Appeal, GoldAnswer, SystemSetting
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
from app.models.rbac import (
    Permission,
    Role,
    RoleConflict,
    RolePermission,
    RoleRequirement,
    UserPlatformRole,
)
from app.models.user import RefreshToken, User, UserActionToken
from app.models.work import (
    Annotation,
    Job,
    JobConfig,
    JobItem,
    Review,
    ReviewError,
    Submission,
    Task,
)

__all__ = [
    "Annotation",
    "Appeal",
    "AuditEvent",
    "Base",
    "DatasetVersion",
    "GoldAnswer",
    "GuidelineVersion",
    "Item",
    "Job",
    "JobConfig",
    "JobItem",
    "Permission",
    "Project",
    "ProjectMember",
    "ProjectTeam",
    "ReasonCode",
    "RefreshToken",
    "Review",
    "ReviewError",
    "Role",
    "RoleConflict",
    "RolePermission",
    "RoleRequirement",
    "Submission",
    "SystemSetting",
    "Task",
    "Team",
    "TeamMember",
    "User",
    "UserActionToken",
    "UserPlatformRole",
]
