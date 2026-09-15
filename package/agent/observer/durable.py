from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from package.agent.database.repositories.executions import ExecutionRepository


class DatabaseExecutionStateReader:
    """Reads canonical execution state from PostgreSQL for observer fallback."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get(self, execution_id: str) -> dict[str, object] | None:
        async with self._session_factory() as session:
            execution = await ExecutionRepository(session).get(execution_id)
            if execution is None:
                return None
            return {
                "execution_id": execution.id,
                "session_id": execution.session_id,
                "question": execution.question,
                "status": execution.status,
                "answer": execution.answer,
                "error": execution.error,
                "result": execution.result,
                "created_at": execution.created_at,
                "updated_at": execution.updated_at,
                "started_at": execution.started_at,
                "completed_at": execution.completed_at,
            }
