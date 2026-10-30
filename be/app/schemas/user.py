import uuid
from datetime import date, datetime
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models.rbac import Role, UserPlatformRole
from app.models.user import User

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
EmploymentType = Literal["full_time", "contractor", "intern"]
UserStatusValue = Literal["active", "suspended", "left"]


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    status: str


class RoleAssignmentRead(BaseModel):
    id: uuid.UUID
    role: str
    granted_at: datetime
    expires_at: datetime | None

    @classmethod
    def build(cls, assignment: UserPlatformRole, role: Role) -> "RoleAssignmentRead":
        return cls(
            id=assignment.id,
            role=role.code,
            granted_at=assignment.granted_at,
            expires_at=assignment.expires_at,
        )


class UserRead(BaseModel):
    id: uuid.UUID
    kind: str
    email: str
    full_name: str
    employee_code: str | None
    status: str
    employment_type: str
    joined_at: date | None
    left_at: date | None
    activated: bool
    platform_roles: list[RoleAssignmentRead]

    @classmethod
    def build(cls, user: User, assignments: list[tuple[UserPlatformRole, Role]]) -> Self:
        return cls(
            id=user.id,
            kind=user.kind,
            email=user.email,
            full_name=user.full_name,
            employee_code=user.employee_code,
            status=user.status,
            employment_type=user.employment_type,
            joined_at=user.joined_at,
            left_at=user.left_at,
            activated=user.is_activated,
            platform_roles=[RoleAssignmentRead.build(a, r) for a, r in assignments],
        )


class UserCreate(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    full_name: str = Field(min_length=1, max_length=200)
    employment_type: EmploymentType
    employee_code: str | None = Field(default=None, max_length=64)
    joined_at: date | None = None


class ActivationLinkRead(BaseModel):
    activation_url: str
    activation_expires_at: datetime


class UserCreated(ActivationLinkRead):
    user: UserRead


class DisableUserRequest(BaseModel):
    status: Literal["suspended", "left"]
    reason: str = Field(min_length=3, max_length=500)


class GrantRoleRequest(BaseModel):
    role: str = Field(min_length=1, max_length=64)
    expires_at: AwareDatetime | None = None
    acknowledge_warning: bool = False


class ExtendRoleRequest(BaseModel):
    expires_at: AwareDatetime | None


class RevokeRoleRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class ExpiringRoleRead(RoleAssignmentRead):
    user: UserSummary


class MeRead(UserRead):
    pass


class MyPermissions(BaseModel):
    permissions: dict[str, list[str]]
