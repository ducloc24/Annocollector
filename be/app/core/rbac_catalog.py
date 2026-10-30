"""Role/permission catalog: the single source for the seed migration and for code.

Mirrors docs/database_design.md sections 3.3-3.5. The seed migration reads this module
once; changing the matrix later requires a new migration, not just an edit here.
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum

CATALOG_NAMESPACE = uuid.UUID("6f1d3c52-8a8e-4c55-9d1b-2f0e7a6c4b10")


class RoleScope(StrEnum):
    PLATFORM = "platform"
    PROJECT = "project"
    TEAM = "team"


class PermissionLevel(StrEnum):
    PLATFORM = "platform"
    PROJECT = "project"
    TEAM = "team"
    ANY = "any"  # checked at platform or project level (audit.read)


class Limit(StrEnum):
    ALL = "all"  # whole system
    PROJECT = "project"  # projects the user belongs to
    ASSIGNED = "assigned"  # only jobs assigned to the user
    OWN = "own"  # only the user's own records
    TEAM = "team"  # only the user's own team
    RBAC = "rbac"  # audit.read for hr_admin: only access-control events


class Perm(StrEnum):
    USER_MANAGE = "user.manage"
    PLATFORM_ROLE_GRANT = "platform_role.grant"
    PROJECT_CREATE = "project.create"
    PROJECT_UPDATE = "project.update"
    GUIDELINE_MANAGE = "guideline.manage"
    DATASET_UPLOAD = "dataset.upload"
    DATASET_DELETE = "dataset.delete"
    DATASET_READ = "dataset.read"
    JOB_CONFIG_MANAGE = "job_config.manage"
    MEMBER_MANAGE = "member.manage"
    TASK_MANAGE = "task.manage"
    JOB_ASSIGN = "job.assign"
    JOB_ANNOTATE = "job.annotate"
    JOB_REVIEW = "job.review"
    REVIEW_OVERRIDE = "review.override"
    TASK_ACCEPT = "task.accept"
    APPEAL_OPEN = "appeal.open"
    APPEAL_DECIDE = "appeal.decide"
    PROGRESS_READ = "progress.read"
    QUALITY_READ = "quality.read"
    AUDIT_READ = "audit.read"
    SYSTEM_CONFIGURE = "system.configure"
    DATASET_BREAKGLASS = "dataset.breakglass"
    EXPORT_DATA = "export.data"
    TEAM_MANAGE = "team.manage"
    TEAM_READ = "team.read"
    TEAM_MONITOR = "team.monitor"


class PlatformRole(StrEnum):
    HR_ADMIN = "hr_admin"
    PO = "po"
    ANNOTATOR = "annotator"
    REVIEWER = "reviewer"
    PROJECT_MANAGER = "project_manager"
    PLATFORM_ADMIN = "platform_admin"
    AUDITOR = "auditor"


class ProjectRole(StrEnum):
    OWNER = "owner"
    MANAGER = "manager"
    ANNOTATOR = "annotator"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class TeamRole(StrEnum):
    TEAM_LEAD = "team_lead"


@dataclass(frozen=True)
class RoleDef:
    code: str
    scope: RoleScope
    name: str
    description: str

    @property
    def id(self) -> uuid.UUID:
        return role_id(self.scope, self.code)


@dataclass(frozen=True)
class PermissionDef:
    code: Perm
    level: PermissionLevel
    description: str

    @property
    def id(self) -> uuid.UUID:
        return permission_id(self.code)

    @property
    def resource(self) -> str:
        return self.code.split(".", 1)[0]

    @property
    def action(self) -> str:
        return self.code.split(".", 1)[1]


def role_id(scope: RoleScope | str, code: str) -> uuid.UUID:
    return uuid.uuid5(CATALOG_NAMESPACE, f"role:{scope}:{code}")


def permission_id(code: str) -> uuid.UUID:
    return uuid.uuid5(CATALOG_NAMESPACE, f"permission:{code}")


P, J, T = RoleScope.PLATFORM, RoleScope.PROJECT, RoleScope.TEAM

ROLES: tuple[RoleDef, ...] = (
    RoleDef(PlatformRole.HR_ADMIN, P, "HR admin", "Tạo user, cấp và thu hồi role platform"),
    RoleDef(PlatformRole.PO, P, "Product Owner", "Tạo project, cấu hình, nghiệm thu"),
    RoleDef(PlatformRole.ANNOTATOR, P, "Annotator", "Năng lực gán nhãn"),
    RoleDef(PlatformRole.REVIEWER, P, "Reviewer", "Năng lực chấm"),
    RoleDef(PlatformRole.PROJECT_MANAGER, P, "Project manager", "Điều phối, tiến độ"),
    RoleDef(PlatformRole.PLATFORM_ADMIN, P, "Platform admin", "Vận hành hệ thống"),
    RoleDef(PlatformRole.AUDITOR, P, "Auditor", "Chỉ đọc audit và báo cáo"),
    RoleDef(ProjectRole.OWNER, J, "Owner", "Toàn quyền trong project"),
    RoleDef(ProjectRole.MANAGER, J, "Manager", "Chia job, theo dõi tiến độ"),
    RoleDef(ProjectRole.ANNOTATOR, J, "Annotator", "Làm job được giao (qua đội)"),
    RoleDef(ProjectRole.REVIEWER, J, "Reviewer", "Chấm job (qua đội)"),
    RoleDef(ProjectRole.VIEWER, J, "Viewer", "Chỉ đọc tiến độ và báo cáo"),
    RoleDef(TeamRole.TEAM_LEAD, T, "Trưởng nhóm", "Xem số liệu và cảnh báo của đội"),
)

L = PermissionLevel
PERMISSIONS: tuple[PermissionDef, ...] = (
    PermissionDef(Perm.USER_MANAGE, L.PLATFORM, "Tạo, sửa, disable user"),
    PermissionDef(Perm.PLATFORM_ROLE_GRANT, L.PLATFORM, "Cấp, thu hồi role platform"),
    PermissionDef(Perm.PROJECT_CREATE, L.PLATFORM, "Tạo project"),
    PermissionDef(Perm.PROJECT_UPDATE, L.PROJECT, "Sửa project"),
    PermissionDef(Perm.GUIDELINE_MANAGE, L.PROJECT, "Tạo version guideline"),
    PermissionDef(Perm.DATASET_UPLOAD, L.PROJECT, "Upload, thay version dataset"),
    PermissionDef(Perm.DATASET_DELETE, L.PROJECT, "Xoá dataset"),
    PermissionDef(Perm.DATASET_READ, L.PROJECT, "Xem nội dung dataset và item"),
    PermissionDef(Perm.JOB_CONFIG_MANAGE, L.PROJECT, "Tạo version job config"),
    PermissionDef(
        Perm.MEMBER_MANAGE, L.PROJECT, "Thêm, gỡ thành viên trực tiếp; gắn, gỡ đội khỏi project"
    ),
    PermissionDef(Perm.TASK_MANAGE, L.PROJECT, "Tạo, cắt task; giao task cho đội"),
    PermissionDef(Perm.JOB_ASSIGN, L.PROJECT, "Chia job, đổi người làm"),
    PermissionDef(Perm.JOB_ANNOTATE, L.PROJECT, "Làm và submit job"),
    PermissionDef(Perm.JOB_REVIEW, L.PROJECT, "Chấm job: accept, reject, escalate"),
    PermissionDef(Perm.REVIEW_OVERRIDE, L.PROJECT, "Đổi quyết định của reviewer"),
    PermissionDef(Perm.TASK_ACCEPT, L.PROJECT, "Nghiệm thu task"),
    PermissionDef(Perm.APPEAL_OPEN, L.PROJECT, "Mở khiếu nại"),
    PermissionDef(Perm.APPEAL_DECIDE, L.PROJECT, "Xử lý khiếu nại"),
    PermissionDef(Perm.PROGRESS_READ, L.PROJECT, "Xem tiến độ"),
    PermissionDef(Perm.QUALITY_READ, L.PROJECT, "Xem báo cáo chất lượng"),
    PermissionDef(Perm.AUDIT_READ, L.ANY, "Đọc audit log"),
    PermissionDef(Perm.SYSTEM_CONFIGURE, L.PLATFORM, "Cấu hình hệ thống, service account"),
    PermissionDef(Perm.DATASET_BREAKGLASS, L.PLATFORM, "Truy cập dataset khẩn cấp"),
    PermissionDef(Perm.EXPORT_DATA, L.PROJECT, "Export dữ liệu và báo cáo"),
    PermissionDef(Perm.TEAM_MANAGE, L.PLATFORM, "Tạo đội, quản lý thành viên đội"),
    PermissionDef(Perm.TEAM_READ, L.PLATFORM, "Xem danh sách đội để chọn"),
    PermissionDef(Perm.TEAM_MONITOR, L.TEAM, "Xem số liệu và cảnh báo của đội mình"),
)

A = Limit.ALL
PRJ = Limit.PROJECT
ASG = Limit.ASSIGNED
OWN = Limit.OWN

# (scope, role code) -> {permission: limit}
ROLE_PERMISSIONS: dict[tuple[RoleScope, str], dict[Perm, Limit]] = {
    (P, PlatformRole.HR_ADMIN): {
        Perm.USER_MANAGE: A,
        Perm.PLATFORM_ROLE_GRANT: A,
        Perm.AUDIT_READ: Limit.RBAC,
        Perm.TEAM_MANAGE: A,
        Perm.TEAM_READ: A,
    },
    (P, PlatformRole.PO): {Perm.PROJECT_CREATE: A, Perm.TEAM_READ: A},
    (P, PlatformRole.ANNOTATOR): {},
    (P, PlatformRole.REVIEWER): {},
    (P, PlatformRole.PROJECT_MANAGER): {Perm.TEAM_READ: A},
    (P, PlatformRole.PLATFORM_ADMIN): {
        Perm.SYSTEM_CONFIGURE: A,
        Perm.DATASET_BREAKGLASS: A,
        Perm.AUDIT_READ: A,
    },
    (P, PlatformRole.AUDITOR): {Perm.AUDIT_READ: A, Perm.TEAM_READ: A},
    (J, ProjectRole.OWNER): {
        Perm.PROJECT_UPDATE: PRJ,
        Perm.GUIDELINE_MANAGE: PRJ,
        Perm.DATASET_UPLOAD: PRJ,
        Perm.DATASET_DELETE: PRJ,
        Perm.DATASET_READ: PRJ,
        Perm.JOB_CONFIG_MANAGE: PRJ,
        Perm.MEMBER_MANAGE: PRJ,
        Perm.TASK_MANAGE: PRJ,
        Perm.JOB_ASSIGN: PRJ,
        Perm.REVIEW_OVERRIDE: PRJ,
        Perm.TASK_ACCEPT: PRJ,
        Perm.APPEAL_DECIDE: PRJ,
        Perm.PROGRESS_READ: PRJ,
        Perm.QUALITY_READ: PRJ,
        Perm.AUDIT_READ: PRJ,
        Perm.EXPORT_DATA: PRJ,
    },
    (J, ProjectRole.MANAGER): {
        Perm.DATASET_READ: PRJ,
        Perm.MEMBER_MANAGE: PRJ,
        Perm.TASK_MANAGE: PRJ,
        Perm.JOB_ASSIGN: PRJ,
        Perm.APPEAL_DECIDE: PRJ,
        Perm.PROGRESS_READ: PRJ,
        Perm.QUALITY_READ: PRJ,
    },
    (J, ProjectRole.ANNOTATOR): {
        Perm.DATASET_READ: ASG,
        Perm.JOB_ANNOTATE: ASG,
        Perm.APPEAL_OPEN: OWN,
        Perm.PROGRESS_READ: OWN,
        Perm.QUALITY_READ: OWN,
    },
    (J, ProjectRole.REVIEWER): {
        Perm.DATASET_READ: ASG,
        Perm.JOB_REVIEW: ASG,
        Perm.PROGRESS_READ: PRJ,
        Perm.QUALITY_READ: PRJ,
    },
    (J, ProjectRole.VIEWER): {Perm.PROGRESS_READ: PRJ, Perm.QUALITY_READ: PRJ},
    (T, TeamRole.TEAM_LEAD): {Perm.TEAM_MONITOR: Limit.TEAM},
}

# project role -> platform role it requires (viewer requires nothing)
ROLE_REQUIREMENTS: dict[ProjectRole, PlatformRole] = {
    ProjectRole.OWNER: PlatformRole.PO,
    ProjectRole.MANAGER: PlatformRole.PROJECT_MANAGER,
    ProjectRole.ANNOTATOR: PlatformRole.ANNOTATOR,
    ProjectRole.REVIEWER: PlatformRole.REVIEWER,
}


class ConflictScope(StrEnum):
    SAME_PROJECT = "same_project"
    SAME_USER = "same_user"


class ConflictEffect(StrEnum):
    BLOCK = "block"
    WARN = "warn"


@dataclass(frozen=True)
class RoleConflictDef:
    role_a: tuple[RoleScope, str]
    role_b: tuple[RoleScope, str]
    scope: ConflictScope
    effect: ConflictEffect


ROLE_CONFLICTS: tuple[RoleConflictDef, ...] = (
    RoleConflictDef(
        (J, ProjectRole.ANNOTATOR),
        (J, ProjectRole.REVIEWER),
        ConflictScope.SAME_PROJECT,
        ConflictEffect.BLOCK,
    ),
    RoleConflictDef(
        (P, PlatformRole.HR_ADMIN),
        (P, PlatformRole.PLATFORM_ADMIN),
        ConflictScope.SAME_USER,
        ConflictEffect.WARN,
    ),
)


def platform_conflict(a: str, b: str) -> ConflictEffect | None:
    """Effect of a single user holding platform roles ``a`` and ``b`` together."""
    for conflict in ROLE_CONFLICTS:
        if conflict.scope != ConflictScope.SAME_USER:
            continue
        pair = {conflict.role_a, conflict.role_b}
        if pair == {(P, a), (P, b)}:
            return conflict.effect
    return None
