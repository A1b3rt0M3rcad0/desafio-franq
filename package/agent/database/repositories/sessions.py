from typing import Any

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from package.agent.database.models.base import utc_now
from package.agent.database.models.execution import AgentExecution, TERMINAL_EXECUTION_STATUSES
from package.agent.database.models.session import AgentSession


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        metadata: dict[str, Any] | None = None,
        *,
        title: str | None = None,
    ) -> AgentSession:
        entity = AgentSession(title=title, metadata_json=metadata or {})
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def get(self, session_id: str) -> AgentSession | None:
        return await self._session.get(AgentSession, session_id)

    async def list_recent(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        only_with_executions: bool = False,
    ) -> list[AgentSession]:
        if limit < 1:
            raise ValueError("limit must be greater than zero")
        if offset < 0:
            raise ValueError("offset cannot be negative")

        statement = select(AgentSession)
        if only_with_executions:
            statement = statement.where(
                exists(
                    select(AgentExecution.id).where(
                        AgentExecution.session_id == AgentSession.id
                    )
                )
            )
        result = await self._session.scalars(
            statement.order_by(
                AgentSession.updated_at.desc(),
                AgentSession.created_at.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        return list(result)

    async def update_title(self, entity: AgentSession, title: str) -> AgentSession:
        entity.title = title
        entity.updated_at = utc_now()
        await self._session.flush()
        return entity

    async def touch(self, entity: AgentSession) -> None:
        entity.updated_at = utc_now()
        await self._session.flush()

    async def execution_ids(self, session_id: str) -> list[str]:
        result = await self._session.scalars(
            select(AgentExecution.id).where(AgentExecution.session_id == session_id)
        )
        return list(result)

    async def has_active_executions(self, session_id: str) -> bool:
        statement = select(
            exists().where(
                AgentExecution.session_id == session_id,
                AgentExecution.status.not_in(TERMINAL_EXECUTION_STATUSES),
            )
        )
        return bool(await self._session.scalar(statement))

    async def delete(self, session_id: str) -> bool:
        result = await self._session.execute(
            delete(AgentSession).where(AgentSession.id == session_id)
        )
        await self._session.flush()
        return bool(result.rowcount)
