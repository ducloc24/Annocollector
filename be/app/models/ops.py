import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class AppealStatus(StrEnum):
    OPEN = "open"  # waiting for the project manager (step 1)
    PO_DECISION = "po_decision"  # forwarded to an owner
    CLOSED = "closed"


class AppealOutcome(StrEnum):
    UPHELD = "upheld"  # the reject stands
    OVERTURNED = "overturned"  # the job is accepted after all


class Appeal(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "appeals"

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id"), index=True, nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), index=True, nullable=False
    )
    review_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reviews.id"), nullable=False)
    opened_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=AppealStatus.OPEN, nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(16))
    resolution: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GoldAnswer(UUIDPrimaryKeyMixin, Base):
    """Expected labels of a gold job. Only quality reports read this table."""

    __tablename__ = "gold_answers"
    __table_args__ = (UniqueConstraint("job_id", "item_id", "target", name="uq_gold_answers"),)

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id"), index=True, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id"), nullable=False)
    target: Mapped[str | None] = mapped_column(String(64))
    expected: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
