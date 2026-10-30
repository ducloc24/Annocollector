import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class JobConfigDraft(BaseModel):
    item_type: str = "tool_call"
    label_schema: dict[str, Any]
    job_rules: dict[str, Any] = Field(default_factory=dict)
    self_check: list[str] = Field(default_factory=list)


class JobConfigValidation(BaseModel):
    valid: bool
    errors: list[str]
    job_rules: dict[str, Any]


class JobConfigRead(ORM):
    id: uuid.UUID
    version: int
    item_type: str
    label_schema: dict[str, Any]
    job_rules: dict[str, Any]
    self_check: list[str]
    created_by: uuid.UUID
    created_at: datetime


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    dataset_version: int = Field(ge=1)
    job_config_version: int = Field(ge=1)
    guideline_version: int = Field(ge=1)
    team_id: uuid.UUID | None = None
    priority: int = Field(default=0, ge=-100, le=100)


class TaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    priority: int | None = Field(default=None, ge=-100, le=100)


class TaskTeam(BaseModel):
    team_id: uuid.UUID


class TaskRead(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    priority: int
    team_id: uuid.UUID | None
    dataset_version_id: uuid.UUID
    job_config_id: uuid.UUID
    guideline_version_id: uuid.UUID
    created_at: datetime
    delivered_at: datetime | None
    jobs_total: int
    by_status: dict[str, int]


class TaskCreated(BaseModel):
    task: TaskRead
    jobs: int


class JobRead(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    task_id: uuid.UUID
    ordinal: int
    status: str
    assignee_id: uuid.UUID | None
    reviewer_id: uuid.UUID | None
    rework_count: int
    has_unsure: bool
    lease_expires_at: datetime | None
    assigned_at: datetime | None
    submitted_at: datetime | None
    closed_at: datetime | None


class DraftRequest(BaseModel):
    draft: dict[str, Any]


class AnnotationIn(BaseModel):
    item_id: uuid.UUID
    target: str = Field(min_length=1, max_length=64)
    value: dict[str, Any]


class SubmitRequest(BaseModel):
    annotations: list[AnnotationIn] = Field(max_length=5000)
    self_check: list[bool] = Field(default_factory=list)


class SubmitResult(BaseModel):
    job_id: uuid.UUID
    status: str
    round: int


class Pair(BaseModel):
    job_id: uuid.UUID
    user_id: uuid.UUID


class PairsRequest(BaseModel):
    assignments: list[Pair] = Field(min_length=1, max_length=500)


class ReviewErrorIn(BaseModel):
    item_id: uuid.UUID
    target: str | None = Field(default=None, max_length=64)
    reason_code: str = Field(min_length=1, max_length=64)
    severity: Literal["critical", "major", "minor"]
    note: str | None = Field(default=None, max_length=2000)


class ReviewRequest(BaseModel):
    decision: Literal["accept", "accept_with_fix", "reject", "escalate"]
    reason: str | None = Field(default=None, max_length=2000)
    errors: list[ReviewErrorIn] = Field(default_factory=list, max_length=1000)


class ReviewResult(BaseModel):
    review_id: uuid.UUID
    job_status: str
    rework_count: int


class EscalationDecisionRequest(BaseModel):
    decision: Literal["accept", "reject"]
    reason: str = Field(min_length=3, max_length=2000)
    guideline_issue: bool = False


class ReReviewRequest(BaseModel):
    job_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=3, max_length=2000)
