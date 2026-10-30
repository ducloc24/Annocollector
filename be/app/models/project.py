import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"


class DataClassification(StrEnum):
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class TeamStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default=ProjectStatus.DRAFT, nullable=False)
    data_classification: Mapped[str] = mapped_column(
        String(16), default=DataClassification.INTERNAL, nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class ProjectMember(UUIDPrimaryKeyMixin, Base):
    """Direct project roles: owner, manager, viewer. Annotators/reviewers come via teams."""

    __tablename__ = "project_members"
    __table_args__ = (
        Index(
            "uq_project_members_active",
            "project_id",
            "user_id",
            "role_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), nullable=False)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GuidelineVersion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Append-only. Holds the rubric too (decided: rubric lives inside the guideline)."""

    __tablename__ = "guideline_versions"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_guideline_versions"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class Team(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "teams"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default=TeamStatus.ACTIVE, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class TeamMember(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "team_members"
    __table_args__ = (
        Index(
            "uq_team_members_active",
            "team_id",
            "user_id",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
        Index(
            "uq_team_members_lead",
            "team_id",
            unique=True,
            postgresql_where=text("is_lead AND removed_at IS NULL"),
        ),
    )

    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    team_role: Mapped[str] = mapped_column(String(16), nullable=False)
    is_lead: Mapped[bool] = mapped_column(default=False, nullable=False)
    added_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remove_reason: Mapped[str | None] = mapped_column(String(500))


class ProjectTeam(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "project_teams"
    __table_args__ = (
        Index(
            "uq_project_teams_active",
            "project_id",
            "team_id",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), index=True, nullable=False
    )
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), index=True, nullable=False)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReasonCode(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "reason_codes"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_reason_codes"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    default_severity: Mapped[str] = mapped_column(String(16), default="major", nullable=False)
    # label: annotator picks it while labelling; review: reviewer records it; both: either.
    applies_to: Mapped[str] = mapped_column(String(16), default="both", nullable=False)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)


class DatasetVersion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_dataset_versions"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    checksum: Mapped[str] = mapped_column(String(80), nullable=False)
    item_count: Mapped[int] = mapped_column(nullable=False)
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    parser: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_options: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)
    parse_report: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Item(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "items"
    __table_args__ = (Index("ix_items_dataset_ordinal", "dataset_version_id", "ordinal"),)

    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dataset_versions.id"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(nullable=False)
    external_ref: Mapped[str | None] = mapped_column(String(200))
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
