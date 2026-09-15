from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from package.agent.database.models.outbox import OutboxMessage, OutboxStatus


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(
        self,
        *,
        event_type: str,
        aggregate_id: str,
        payload: dict[str, Any],
    ) -> OutboxMessage:
        message = OutboxMessage(
            event_type=event_type,
            aggregate_id=aggregate_id,
            payload=payload,
        )
        self._session.add(message)
        await self._session.flush()
        return message

    async def claim_batch(self, *, runner_id: str, limit: int) -> list[OutboxMessage]:
        now = _utc_now()
        statement = (
            select(OutboxMessage)
            .where(
                OutboxMessage.status == OutboxStatus.PENDING.value,
                OutboxMessage.available_at <= now,
            )
            .order_by(OutboxMessage.created_at)
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
        rows = list((await self._session.scalars(statement)).all())
        for row in rows:
            row.status = OutboxStatus.PROCESSING.value
            row.locked_at = now
            row.locked_by = runner_id
            row.attempts += 1
        await self._session.flush()
        return rows

    async def mark_processed(self, message: OutboxMessage) -> None:
        message.status = OutboxStatus.PROCESSED.value
        message.processed_at = _utc_now()
        message.locked_at = None
        message.locked_by = None
        await self._session.flush()

    async def release_with_error(
        self,
        message: OutboxMessage,
        *,
        error: str,
        retry_delay_seconds: float,
    ) -> None:
        message.status = OutboxStatus.PENDING.value
        message.available_at = _utc_now() + timedelta(seconds=retry_delay_seconds)
        message.locked_at = None
        message.locked_by = None
        message.last_error = error[:1000]
        await self._session.flush()
