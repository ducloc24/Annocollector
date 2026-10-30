import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.schemas.user import UserSummary

CODE_PATTERN = r"^[A-Za-z0-9_-]{2,64}$"
Classification = Literal["internal", "confidential", "restricted"]
Severity = Literal["critical", "major", "minor"]
AppliesTo = Literal["label", "review", "both"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- projects ----------


class ProjectCreate(BaseModel):
    code: str = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    data_classification: Classification = "internal"


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    data_classification: Classification | None = None


class ProjectRead(ORM):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    status: str
    data_classification: str
    owner_id: uuid.UUID
    created_at: datetime


class ProjectWithAccess(ProjectRead):
    my_roles: list[str]
    my_permissions: list[str]


class MemberCreate(BaseModel):
    user_id: uuid.UUID
    role: Literal["owner", "manager", "viewer"]
    expires_at: AwareDatetime | None = None


class MemberRead(BaseModel):
    id: uuid.UUID
    user: UserSummary
    role: str
    assigned_at: datetime
    expires_at: datetime | None


class ProjectTeamCreate(BaseModel):
    team_id: uuid.UUID


class ProjectTeamRead(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    code: str
    name: str
    annotators: int
    reviewers: int
    assigned_at: datetime


class ProjectTeamLinked(BaseModel):
    link: ProjectTeamRead
    warnings: list[str]


# ---------- guidelines and reason codes ----------


class GuidelineCreate(BaseModel):
    content: str = Field(min_length=1, max_length=200_000)


class GuidelineSummary(ORM):
    id: uuid.UUID
    version: int
    created_by: uuid.UUID
    created_at: datetime


class GuidelineRead(GuidelineSummary):
    content: str


class ReasonCodeCreate(BaseModel):
    code: str = Field(pattern=r"^[A-Za-z0-9_]{2,64}$")
    label: str = Field(min_length=1, max_length=200)
    default_severity: Severity = "major"
    applies_to: AppliesTo = "both"


class ReasonCodeUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    default_severity: Severity | None = None
    applies_to: AppliesTo | None = None
    active: bool | None = None


class ReasonCodeRead(ORM):
    id: uuid.UUID
    code: str
    label: str
    default_severity: str
    applies_to: str
    active: bool


# ---------- teams ----------


class TeamCreate(BaseModel):
    code: str = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: Literal["active", "archived"] | None = None


class TeamMemberRead(BaseModel):
    id: uuid.UUID
    user: UserSummary
    team_role: str
    is_lead: bool
    added_at: datetime
    expires_at: datetime | None


class TeamRead(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    status: str
    annotators: int
    reviewers: int
    lead: UserSummary | None


class TeamDetail(TeamRead):
    members: list[TeamMemberRead]


class TeamMemberCreate(BaseModel):
    user_id: uuid.UUID
    team_role: Literal["annotator", "reviewer"]
    expires_at: AwareDatetime | None = None


class TeamMemberUpdate(BaseModel):
    team_role: Literal["annotator", "reviewer"] | None = None
    is_lead: bool | None = None
    expires_at: AwareDatetime | None = None


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class MyTeam(BaseModel):
    team_id: uuid.UUID
    code: str
    name: str
    team_role: str
    is_lead: bool


# ---------- datasets ----------


class UploadUrlRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    size: int = Field(ge=1)


class UploadUrlRead(BaseModel):
    upload_key: str
    url: str
    expires_in: int


class DatasetRequest(BaseModel):
    upload_key: str = Field(min_length=1, max_length=512)
    parser: str = "jsonl_chat"
    parser_options: dict[str, str] = Field(default_factory=dict)


class DatasetRead(ORM):
    id: uuid.UUID
    version: int
    item_count: int
    item_type: str
    checksum: str
    parser: str
    parser_options: dict[str, Any]
    parser_version: str
    parse_report: dict[str, Any]
    created_at: datetime


class ItemRead(ORM):
    id: uuid.UUID
    ordinal: int
    external_ref: str | None
    item_type: str
    payload: dict[str, Any]


class ParserRead(BaseModel):
    name: str
    version: str
    item_type: str
    description: str
    default_options: dict[str, str]


class ItemTypeRead(BaseModel):
    name: str
    description: str
    field_types: list[str]
    default_label_schema: dict[str, Any] | None
