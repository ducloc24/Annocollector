import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin


class TaskStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DELIVERED = "delivered"


class JobStatus(StrEnum):
    UNASSIGNED = "unassigned"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    ACCEPTED = "accepted"
    ACCEPTED_WITH_FIX = "accepted_with_fix"
    REJECTED = "rejected"
    ESCALATED = "escalated"


CLOSED_JOB_STATUSES = (JobStatus.ACCEPTED, JobStatus.ACCEPTED_WITH_FIX)


class ReviewKind(StrEnum):
    REVIEW = "review"
    ESCALATION_DECISION = "escalation_decision"
    RE_REVIEW = "re_review"
    OVERRIDE = "override"
    APPEAL_DECISION = "appeal_decision"
    AUTO_ACCEPT = "auto_accept"


class Decision(StrEnum):
    ACCEPT = "accept"
    ACCEPT_WITH_FIX = "accept_with_fix"
    REJECT = "reject"
    ESCALATE = "escalate"
    REOPEN = "reopen"


class JobConfig(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Append-only: what a job is (item type, label schema, rules, self-check)."""

    __tablename__ = "job_configs"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_job_configs"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    label_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    job_rules: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    self_check: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tasks"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dataset_versions.id"), nullable=False
    )
    job_config_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_configs.id"), nullable=False)
    guideline_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("guideline_versions.id"), nullable=False
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"), index=True)
    priority: Mapped[int] = mapped_column(default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=TaskStatus.DRAFT, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    signed_off_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Job(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_project_status", "project_id", "status"),
        Index("ix_jobs_task_status_created", "task_id", "status", "created_at"),
        Index("ix_jobs_assignee_status", "assignee_id", "status"),
        Index("ix_jobs_reviewer_status", "reviewer_id", "status"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    guideline_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("guideline_versions.id"), nullable=False
    )
    job_config_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_configs.id"), nullable=False)
    ordinal: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=JobStatus.UNASSIGNED, nullable=False)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    last_reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rework_count: Mapped[int] = mapped_column(default=0, nullable=False)
    has_unsure: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_gold: Mapped[bool] = mapped_column(default=False, nullable=False)
    draft: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    draft_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobItem(Base):
    __tablename__ = "job_items"

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id"), primary_key=True)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id"), primary_key=True, index=True)
    position: Mapped[int] = mapped_column(nullable=False)


class Submission(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("job_id", "round", name="uq_submissions_round"),)

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id"), index=True, nullable=False)
    round: Mapped[int] = mapped_column(nullable=False)
    annotator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    self_check_result: Mapped[list[bool]] = mapped_column(JSONB, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Annotation(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "annotations"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id"), index=True, nullable=False
    )
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id"), nullable=False)
    target: Mapped[str | None] = mapped_column(String(64))
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_unsure: Mapped[bool] = mapped_column(default=False, nullable=False)


class Review(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Append-only. A later decision is a new row pointing at the one it supersedes."""

    __tablename__ = "reviews"

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id"), index=True, nullable=False)
    submission_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("submissions.id"))
    # Null for auto-accepted jobs (review sampling).
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    supersedes_review_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("reviews.id"))
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    guideline_issue: Mapped[bool] = mapped_column(default=False, nullable=False)


class ReviewError(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "review_errors"

    review_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reviews.id"), index=True, nullable=False
    )
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id"), nullable=False)
    target: Mapped[str | None] = mapped_column(String(64))
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
