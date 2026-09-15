from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from package.agent.database.models.trace import ExecutionTrace


class TraceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        *,
        execution_id: str,
        sequence: int,
        event_type: str,
        payload: dict,
    ) -> ExecutionTrace:
        trace = ExecutionTrace(
            execution_id=execution_id,
            sequence=sequence,
            event_type=event_type,
            payload=payload,
        )
        self._session.add(trace)
        await self._session.flush()
        return trace

    async def list_for_execution(self, execution_id: str) -> list[ExecutionTrace]:
        statement = (
            select(ExecutionTrace)
            .where(ExecutionTrace.execution_id == execution_id)
            .order_by(ExecutionTrace.sequence)
        )
        return list((await self._session.scalars(statement)).all())
