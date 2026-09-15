from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from package.agent.cache.execution_state import ExecutionHotState
from package.agent.database.repositories.executions import ExecutionRepository
from package.agent.database.repositories.outbox import OutboxRepository
from package.agent.database.repositories.sessions import SessionRepository
from package.api.http.dependencies import get_hot_state, get_session_factory
from package.api.http.schemas.execution import CreateExecutionRequest, ExecutionResponse
from package.api.presentation.execution import present_execution

router = APIRouter(tags=["executions"])


@router.get(
    "/sessions/{session_id}/executions",
    response_model=list[ExecutionResponse],
)
async def list_session_executions(
    session_id: str,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> list[ExecutionResponse]:
    async with session_factory() as db:
        if await SessionRepository(db).get(session_id) is None:
            raise HTTPException(status_code=404, detail="Session not found")
        executions = await ExecutionRepository(db).list_by_session(session_id)
        return [present_execution(execution) for execution in executions]


@router.post(
    "/sessions/{session_id}/executions",
    response_model=ExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_execution(
    session_id: str,
    request: CreateExecutionRequest,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> ExecutionResponse:
    """Accept the execution durably; provider availability belongs to the Runner.

    The API owns acceptance only. It persists the Execution and Outbox message in
    the same transaction and returns 202. A degraded Runner can then consume the
    request and mark the Execution as failed, which keeps the failure observable
    through the normal Observer/SSE path instead of short-circuiting in the API.
    """
    async with session_factory() as db:
        if await SessionRepository(db).get(session_id) is None:
            raise HTTPException(status_code=404, detail="Session not found")

        execution = await ExecutionRepository(db).create(session_id, request.question)
        await OutboxRepository(db).enqueue(
            event_type="execution.requested",
            aggregate_id=execution.id,
            payload={
                "execution_id": execution.id,
                "session_id": session_id,
                "question": request.question,
            },
        )
        await db.commit()
        return present_execution(execution)


@router.get("/executions/{execution_id}", response_model=ExecutionResponse)
async def get_execution(
    execution_id: str,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
    hot_state: ExecutionHotState = Depends(get_hot_state),
) -> ExecutionResponse:
    async with session_factory() as db:
        execution = await ExecutionRepository(db).get(execution_id)
        if execution is None:
            raise HTTPException(status_code=404, detail="Execution not found")
        response = present_execution(execution)

    hot = await hot_state.get(execution_id)
    if hot and response.status == "running" and hot.get("partial_answer"):
        response.answer = str(hot["partial_answer"])
    return response
