import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin


class UserKind(StrEnum):
    HUMAN = "human"
    SERVICE = "service"


class UserStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    LEFT = "left"


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    CONTRACTOR = "contractor"
    INTERN = "intern"


class ActionTokenPurpose(StrEnum):
    ACTIVATE = "activate"
    RESET_PASSWORD = "reset_password"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    kind: Mapped[str] = mapped_column(String(16), default=UserKind.HUMAN, nullable=False)
    employee_code: Mapped[str | None] = mapped_column(String(64), unique=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=UserStatus.ACTIVE, nullable=False)
    employment_type: Mapped[str] = mapped_column(String(16), nullable=False)
    joined_at: Mapped[date | None] = mapped_column(Date)
    left_at: Mapped[date | None] = mapped_column(Date)
    # Null until the user activates the account and sets a password.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    # Bumped to invalidate every access token issued before (offboarding, password change).
    token_version: Mapped[int] = mapped_column(default=0, nullable=False)

    @property
    def is_activated(self) -> bool:
        return self.password_hash is not None


class RefreshToken(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("refresh_tokens.id"))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserActionToken(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "user_action_tokens"
    __table_args__ = (
        Index(
            "uq_user_action_tokens_open",
            "user_id",
            "purpose",
            unique=True,
            postgresql_where=text("used_at IS NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
