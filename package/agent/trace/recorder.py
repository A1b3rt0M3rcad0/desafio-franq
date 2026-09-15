from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from package.agent.database.repositories.traces import TraceRepository
from package.agent.observer.events import ExecutionEvent


class TraceRecorder:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record(self, event: ExecutionEvent, *, sequence: int) -> None:
        async with self._session_factory() as session:
            repository = TraceRepository(session)
            await repository.append(
                execution_id=event.execution_id,
                sequence=sequence,
                event_type=event.type.value,
                payload=event.payload,
            )
            await session.commit()
