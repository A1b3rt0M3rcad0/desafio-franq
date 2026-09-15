"""Add durable conversation titles to agent sessions.

Revision ID: 0002_add_session_titles
Revises: 0001_initial_schema
Create Date: 2026-09-15
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002_add_session_titles"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_sessions",
        sa.Column("title", sa.String(length=160), nullable=True),
    )

    op.execute(
        """
        UPDATE agent_sessions AS session
        SET title = COALESCE(
            NULLIF(BTRIM(session.metadata_json ->> 'title'), ''),
            (
                SELECT CASE
                    WHEN LENGTH(normalized.question) <= 56 THEN normalized.question
                    ELSE RTRIM(SUBSTRING(normalized.question FROM 1 FOR 53)) || '...'
                END
                FROM (
                    SELECT REGEXP_REPLACE(execution.question, '\\s+', ' ', 'g') AS question
                    FROM agent_executions AS execution
                    WHERE execution.session_id = session.id
                    ORDER BY execution.created_at ASC
                    LIMIT 1
                ) AS normalized
            )
        )
        """
    )


def downgrade() -> None:
    op.drop_column("agent_sessions", "title")
