"""Create the durable agent schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-15
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "agent_executions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_executions_session_id", "agent_executions", ["session_id"])
    op.create_index("ix_agent_executions_status", "agent_executions", ["status"])

    op.create_table(
        "outbox_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=36), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outbox_messages_aggregate_id", "outbox_messages", ["aggregate_id"])
    op.create_index("ix_outbox_messages_available_at", "outbox_messages", ["available_at"])
    op.create_index("ix_outbox_messages_event_type", "outbox_messages", ["event_type"])
    op.create_index("ix_outbox_messages_status", "outbox_messages", ["status"])

    op.create_table(
        "context_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("execution_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("estimated_tokens", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["execution_id"], ["agent_executions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "sequence",
            name="uq_context_snapshot_session_sequence",
        ),
    )
    op.create_index("ix_context_snapshots_execution_id", "context_snapshots", ["execution_id"])
    op.create_index("ix_context_snapshots_session_id", "context_snapshots", ["session_id"])

    op.create_table(
        "global_context_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("execution_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["execution_id"], ["agent_executions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "sequence",
            name="uq_global_context_session_sequence",
        ),
    )
    op.create_index(
        "ix_global_context_entries_execution_id",
        "global_context_entries",
        ["execution_id"],
    )
    op.create_index("ix_global_context_entries_kind", "global_context_entries", ["kind"])
    op.create_index("ix_global_context_entries_session_id", "global_context_entries", ["session_id"])

    op.create_table(
        "execution_traces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("execution_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["execution_id"], ["agent_executions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_execution_traces_execution_id", "execution_traces", ["execution_id"])


def downgrade() -> None:
    op.drop_index("ix_execution_traces_execution_id", table_name="execution_traces")
    op.drop_table("execution_traces")

    op.drop_index("ix_global_context_entries_session_id", table_name="global_context_entries")
    op.drop_index("ix_global_context_entries_kind", table_name="global_context_entries")
    op.drop_index("ix_global_context_entries_execution_id", table_name="global_context_entries")
    op.drop_table("global_context_entries")

    op.drop_index("ix_context_snapshots_session_id", table_name="context_snapshots")
    op.drop_index("ix_context_snapshots_execution_id", table_name="context_snapshots")
    op.drop_table("context_snapshots")

    op.drop_index("ix_outbox_messages_status", table_name="outbox_messages")
    op.drop_index("ix_outbox_messages_event_type", table_name="outbox_messages")
    op.drop_index("ix_outbox_messages_available_at", table_name="outbox_messages")
    op.drop_index("ix_outbox_messages_aggregate_id", table_name="outbox_messages")
    op.drop_table("outbox_messages")

    op.drop_index("ix_agent_executions_status", table_name="agent_executions")
    op.drop_index("ix_agent_executions_session_id", table_name="agent_executions")
    op.drop_table("agent_executions")
    op.drop_table("agent_sessions")
