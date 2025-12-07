from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey, Text, func, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.database import Base

if TYPE_CHECKING:
    from src.models.user import User


class IntegrationType(str, Enum):
    GOOGLE = "google"
    ASANA = "asana"
    SLACK = "slack"
    NOTION = "notion"
    TODOIST = "todoist"
    LINKEDIN = "linkedin"
    TWITTER = "twitter"


class Integration(Base):
    __tablename__ = "integrations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[IntegrationType] = mapped_column(SQLEnum(IntegrationType))
    account_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expiry: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scopes: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of scopes
    is_active: Mapped[bool] = mapped_column(default=True)
    last_sync: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="integrations")

    def __repr__(self) -> str:
        return f"<Integration {self.type.value} for user_id={self.user_id}>"
