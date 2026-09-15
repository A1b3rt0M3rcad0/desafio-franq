from typing import Any

from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from package.agent.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AgentSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_sessions"

    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    executions = relationship(
        "AgentExecution",
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="raise",
    )
