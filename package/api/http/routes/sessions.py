from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from package.agent.database.repositories.executions import ExecutionRepository
from package.agent.database.repositories.outbox import OutboxRepository
from package.agent.database.repositories.sessions import SessionRepository
from package.agent.session_title import build_session_title
from package.api.http.dependencies import get_session_factory
from package.api.http.schemas.session import (
    CreateSessionRequest,
    SessionResponse,
    StartedSessionResponse,
    StartSessionRequest,
    UpdateSessionRequest,
)
from package.api.presentation.execution import present_execution
from package.api.presentation.session import present_session

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: CreateSessionRequest,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> SessionResponse:
    """Low-level session creation kept for infrastructure/tests.

    User-facing conversations should use POST /sessions/start so the first
    execution and its outbox message are accepted atomically with the session.
    """

    async with session_factory() as db:
        raw_title = request.metadata.get("title")
        title = str(raw_title).strip() if raw_title else None
        entity = await SessionRepository(db).create(request.metadata, title=title)
        await db.commit()
        return present_session(entity)


@router.post(
    "/start",
    response_model=StartedSessionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_session(
    request: StartSessionRequest,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> StartedSessionResponse:
    """Create a conversation only when its first user message is accepted."""

    async with session_factory() as db:
        session_repository = SessionRepository(db)
        session = await session_repository.create(
            request.metadata,
            title=build_session_title(request.question),
        )
        execution = await ExecutionRepository(db).create(session.id, request.question)
        await OutboxRepository(db).enqueue(
            event_type="execution.requested",
            aggregate_id=execution.id,
            payload={
                "execution_id": execution.id,
                "session_id": session.id,
                "question": request.question,
            },
        )
        await db.commit()
        await db.refresh(session)
        await db.refresh(execution)
        return StartedSessionResponse(
            session=present_session(session),
            execution=present_execution(execution),
        )


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> list[SessionResponse]:
    async with session_factory() as db:
        entities = await SessionRepository(db).list_recent(
            limit=limit,
            offset=offset,
            only_with_executions=True,
        )
        return [present_session(entity) for entity in entities]


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    request: UpdateSessionRequest,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> SessionResponse:
    async with session_factory() as db:
        repository = SessionRepository(db)
        entity = await repository.get(session_id)
        if entity is None:
            raise HTTPException(status_code=404, detail="Session not found")
        await repository.update_title(entity, request.title)
        await db.commit()
        await db.refresh(entity)
        return present_session(entity)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> Response:
    async with session_factory() as db:
        repository = SessionRepository(db)
        entity = await repository.get(session_id)
        if entity is None:
            raise HTTPException(status_code=404, detail="Session not found")
        if await repository.has_active_executions(session_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Não é possível excluir uma conversa com execução ativa.",
            )

        execution_ids = await repository.execution_ids(session_id)
        await OutboxRepository(db).delete_by_aggregate_ids(execution_ids)
        await repository.delete(session_id)
        await db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> SessionResponse:
    async with session_factory() as db:
        entity = await SessionRepository(db).get(session_id)
        if entity is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return present_session(entity)
