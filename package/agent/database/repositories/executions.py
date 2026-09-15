from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from package.agent.database.models.execution import (
    AgentExecution,
    ExecutionStatus,
    TERMINAL_EXECUTION_STATUSES,
)


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

    async def list_by_session(self, session_id: str) -> list[AgentExecution]:
        result = await self._session.scalars(
            select(AgentExecution)
            .where(AgentExecution.session_id == session_id)
            .order_by(AgentExecution.created_at.asc(), AgentExecution.id.asc())
        )
        return list(result.all())

    async def mark_running(self, execution: AgentExecution) -> None:
        if execution.status == ExecutionStatus.CANCEL_REQUESTED.value:
            return
        if execution.status in TERMINAL_EXECUTION_STATUSES:
            return
        execution.status = ExecutionStatus.RUNNING.value
        execution.started_at = _utc_now()
        execution.error = None
        await self._session.flush()

    async def request_cancel(self, execution: AgentExecution) -> bool:
        if execution.status in TERMINAL_EXECUTION_STATUSES:
            return False
        execution.status = ExecutionStatus.CANCEL_REQUESTED.value
        await self._session.flush()
        return True

    async def mark_cancelled(
        self,
        execution: AgentExecution,
        *,
        answer: str | None = None,
    ) -> None:
        if execution.status in {
            ExecutionStatus.COMPLETED.value,
            ExecutionStatus.FAILED.value,
            ExecutionStatus.CANCELLED.value,
        }:
            return
        execution.status = ExecutionStatus.CANCELLED.value
        if answer is not None:
            execution.answer = answer
        execution.completed_at = _utc_now()
        await self._session.flush()

    async def mark_completed(
        self,
        execution: AgentExecution,
        *,
        answer: str,
        result: dict[str, Any] | None = None,
    ) -> None:
        if execution.status in {
            ExecutionStatus.CANCEL_REQUESTED.value,
            ExecutionStatus.CANCELLED.value,
            ExecutionStatus.FAILED.value,
            ExecutionStatus.COMPLETED.value,
        }:
            return
        execution.status = ExecutionStatus.COMPLETED.value
        execution.answer = answer
        execution.result = result
        execution.completed_at = _utc_now()
        await self._session.flush()

    async def mark_failed(self, execution: AgentExecution, error: str) -> None:
        if execution.status in {
            ExecutionStatus.CANCEL_REQUESTED.value,
            ExecutionStatus.CANCELLED.value,
            ExecutionStatus.COMPLETED.value,
            ExecutionStatus.FAILED.value,
        }:
            return
        execution.status = ExecutionStatus.FAILED.value
        execution.error = error[:4000]
        execution.completed_at = _utc_now()
        await self._session.flush()
