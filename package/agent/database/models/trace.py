from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from package.agent.database.models.base import Base, UUIDPrimaryKeyMixin, utc_now


class ExecutionTrace(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "execution_traces"

    execution_id: Mapped[str] = mapped_column(
        ForeignKey("agent_executions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
