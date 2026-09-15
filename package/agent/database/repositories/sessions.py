from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from package.agent.database.models.session import AgentSession


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, metadata: dict[str, Any] | None = None) -> AgentSession:
        entity = AgentSession(metadata_json=metadata or {})
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def get(self, session_id: str) -> AgentSession | None:
        return await self._session.get(AgentSession, session_id)
