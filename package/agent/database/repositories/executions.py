from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from package.agent.database.models.execution import AgentExecution, ExecutionStatus


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, session_id: str, question: str) -> AgentExecution:
        entity = AgentExecution(session_id=session_id, question=question)
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def get(self, execution_id: str) -> AgentExecution | None:
        return await self._session.get(AgentExecution, execution_id)

    async def mark_running(self, execution: AgentExecution) -> None:
        execution.status = ExecutionStatus.RUNNING.value
        execution.started_at = _utc_now()
        execution.error = None
        await self._session.flush()

    async def mark_completed(
        self,
        execution: AgentExecution,
        *,
        answer: str,
        result: dict[str, Any] | None = None,
    ) -> None:
        execution.status = ExecutionStatus.COMPLETED.value
        execution.answer = answer
        execution.result = result
        execution.completed_at = _utc_now()
        await self._session.flush()

    async def mark_failed(self, execution: AgentExecution, error: str) -> None:
        execution.status = ExecutionStatus.FAILED.value
        execution.error = error[:4000]
        execution.completed_at = _utc_now()
        await self._session.flush()
