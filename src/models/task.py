from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey, Text, Integer, func, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.database import Base

if TYPE_CHECKING:
    from src.models.user import User


class TaskSource(str, Enum):
    GOOGLE_CALENDAR = "google_calendar"
    GMAIL = "gmail"
    ASANA = "asana"
    NOTION = "notion"
    TODOIST = "todoist"
    MANUAL = "manual"


class TaskPriority(str, Enum):
    CRITICAL = "critical"  # Must be done today, high impact
    HIGH = "high"  # Important, should be done soon
    MEDIUM = "medium"  # Normal priority
    LOW = "low"  # Can wait, nice to have


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source: Mapped[TaskSource] = mapped_column(SQLEnum(TaskSource))
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Priority scoring
    priority: Mapped[TaskPriority] = mapped_column(
        SQLEnum(TaskPriority), default=TaskPriority.MEDIUM
    )
    ai_priority_score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0-100
    ai_priority_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Dates
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Status
    is_completed: Mapped[bool] = mapped_column(default=False)
    is_urgent: Mapped[bool] = mapped_column(default=False)

    # Metadata
    raw_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON of original data
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="tasks")

    def __repr__(self) -> str:
        return f"<Task {self.title[:30]}... ({self.source.value})>"
