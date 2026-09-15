from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from package.agent.database.repositories.traces import TraceRepository
from package.agent.trace.models import TraceStep
from package.api.http.dependencies import get_session_factory
from package.api.presentation.trace import present_trace

router = APIRouter(prefix="/executions", tags=["trace"])


@router.get("/{execution_id}/trace", response_model=list[TraceStep])
async def get_execution_trace(
    execution_id: str,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> list[TraceStep]:
    async with session_factory() as db:
        traces = await TraceRepository(db).list_for_execution(execution_id)
        return [present_trace(trace) for trace in traces]
