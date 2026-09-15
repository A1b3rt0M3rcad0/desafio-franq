import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import delete

from package.agent.context.models import ContextSummary, GlobalContextKind, SnapshotReason
from package.agent.database.config.connection import create_session_factory
from package.agent.database.config.engine import create_agent_database_engine
from package.agent.database.models.execution import AgentExecution, ExecutionStatus
from package.agent.database.models.session import AgentSession
from package.agent.database.repositories.context import (
    ContextSnapshotRepository,
    GlobalContextRepository,
)


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
    reason="requires the PostgreSQL integration database",
)


async def _create_execution(session_factory):
    session_id = str(uuid4())
    execution_id = str(uuid4())
    async with session_factory() as db, db.begin():
        db.add(AgentSession(id=session_id, metadata_json={}))
        db.add(
            AgentExecution(
                id=execution_id,
                session_id=session_id,
                question="teste de concorrência",
                status=ExecutionStatus.RUNNING.value,
            )
        )
    return session_id, execution_id


async def _cleanup(session_factory, session_id: str) -> None:
    async with session_factory() as db, db.begin():
        await db.execute(delete(AgentSession).where(AgentSession.id == session_id))


@pytest.mark.asyncio
async def test_global_context_sequence_allocation_is_safe_under_concurrency() -> None:
    engine = create_agent_database_engine(os.environ["AGENT_DATABASE_URL"])
    session_factory = create_session_factory(engine)
    session_id, execution_id = await _create_execution(session_factory)
    repository = GlobalContextRepository(session_factory)

    try:
        entries = await asyncio.gather(
            *(
                repository.append(
                    session_id=session_id,
                    execution_id=execution_id,
                    kind=GlobalContextKind.TOOL_RESULT,
                    content=f"result-{index}",
                    metadata={"index": index},
                )
                for index in range(12)
            )
        )
        assert sorted(entry.sequence for entry in entries) == list(range(1, 13))
        assert len({entry.sequence for entry in entries}) == 12
    finally:
        await _cleanup(session_factory, session_id)
        await engine.dispose()


@pytest.mark.asyncio
async def test_snapshot_sequence_allocation_is_safe_under_concurrency() -> None:
    engine = create_agent_database_engine(os.environ["AGENT_DATABASE_URL"])
    session_factory = create_session_factory(engine)
    session_id, execution_id = await _create_execution(session_factory)
    repository = ContextSnapshotRepository(session_factory)
    summary = ContextSummary(current_request="teste")

    try:
        snapshots = await asyncio.gather(
            *(
                repository.create(
                    session_id=session_id,
                    execution_id=execution_id,
                    reason=SnapshotReason.BUDGET_COMPACTION,
                    summary=summary,
                    estimated_tokens=index + 1,
                )
                for index in range(8)
            )
        )
        assert sorted(snapshot.sequence for snapshot in snapshots) == list(range(1, 9))
        assert len({snapshot.sequence for snapshot in snapshots}) == 8
    finally:
        await _cleanup(session_factory, session_id)
        await engine.dispose()
