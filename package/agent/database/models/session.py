from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from package.agent.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AgentSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_sessions"

    title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    executions = relationship(
        "AgentExecution",
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="raise",
        passive_deletes=True,
    )
