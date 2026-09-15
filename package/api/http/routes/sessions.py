from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from package.agent.database.repositories.sessions import SessionRepository
from package.api.http.dependencies import get_session_factory
from package.api.http.schemas.session import CreateSessionRequest, SessionResponse
from package.api.presentation.session import present_session

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: CreateSessionRequest,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> SessionResponse:
    async with session_factory() as db:
        entity = await SessionRepository(db).create(request.metadata)
        await db.commit()
        return present_session(entity)


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    limit: int = Query(default=50, ge=1, le=200),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> list[SessionResponse]:
    async with session_factory() as db:
        entities = await SessionRepository(db).list_recent(limit=limit)
        return [present_session(entity) for entity in entities]


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
