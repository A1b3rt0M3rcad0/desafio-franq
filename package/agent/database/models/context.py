from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from package.agent.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ContextSnapshotRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "context_snapshots"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_context_snapshot_session_sequence"),
    )

    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    execution_id: Mapped[str] = mapped_column(
        ForeignKey("agent_executions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    estimated_tokens: Mapped[int] = mapped_column(Integer, nullable=False)


class GlobalContextEntryRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "global_context_entries"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_global_context_session_sequence"),
    )

    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    execution_id: Mapped[str] = mapped_column(
        ForeignKey("agent_executions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
