from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from package.agent.context.models import (
    ContextSearchMatch,
    ContextSnapshot,
    ContextSummary,
    GlobalContextEntry,
    GlobalContextKind,
    SnapshotReason,
)
from package.agent.context.retrieval import lexical_score, lexical_terms
from package.agent.database.models.context import (
    ContextSnapshotRecord,
    GlobalContextEntryRecord,
)
from package.agent.database.models.session import AgentSession


async def _lock_session(session: AsyncSession, session_id: str) -> None:
    """Serialize sequence allocation for all context records in one session.

    Tool calls may finish concurrently. Locking the durable session row keeps the
    short MAX(sequence) + 1 allocation section serializable without reducing tool
    execution parallelism.
    """
    locked_session_id = await session.scalar(
        select(AgentSession.id)
        .where(AgentSession.id == session_id)
        .with_for_update()
    )
    if locked_session_id is None:
        raise ValueError(f"Session not found: {session_id}")


class ContextSnapshotRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def latest(self, session_id: str) -> ContextSnapshot | None:
        async with self._session_factory() as session:
            record = await session.scalar(
                select(ContextSnapshotRecord)
                .where(ContextSnapshotRecord.session_id == session_id)
                .order_by(ContextSnapshotRecord.sequence.desc())
                .limit(1)
            )
            return _snapshot_from_record(record) if record is not None else None

    async def create(
        self,
        *,
        session_id: str,
        execution_id: str,
        reason: SnapshotReason,
        summary: ContextSummary,
        estimated_tokens: int,
    ) -> ContextSnapshot:
        async with self._session_factory() as session, session.begin():
            await _lock_session(session, session_id)
            current = await session.scalar(
                select(func.max(ContextSnapshotRecord.sequence)).where(
                    ContextSnapshotRecord.session_id == session_id
                )
            )
            record = ContextSnapshotRecord(
                session_id=session_id,
                execution_id=execution_id,
                sequence=(current or 0) + 1,
                reason=reason.value,
                summary_json=summary.model_dump(mode="json"),
                estimated_tokens=estimated_tokens,
            )
            session.add(record)
            await session.flush()
            await session.refresh(record)
            return _snapshot_from_record(record)


class GlobalContextRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def append(
        self,
        *,
        session_id: str,
        execution_id: str,
        kind: GlobalContextKind,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> GlobalContextEntry:
        async with self._session_factory() as session, session.begin():
            await _lock_session(session, session_id)
            current = await session.scalar(
                select(func.max(GlobalContextEntryRecord.sequence)).where(
                    GlobalContextEntryRecord.session_id == session_id
                )
            )
            record = GlobalContextEntryRecord(
                session_id=session_id,
                execution_id=execution_id,
                sequence=(current or 0) + 1,
                kind=kind.value,
                content=content,
                metadata_json=metadata or {},
            )
            session.add(record)
            await session.flush()
            await session.refresh(record)
            return _entry_from_record(record)

    async def search(
        self,
        *,
        session_id: str,
        query: str,
        limit: int,
    ) -> list[ContextSearchMatch]:
        terms = lexical_terms(query)
        if not terms:
            return []

        async with self._session_factory() as session:
            records = list(
                (
                    await session.scalars(
                        select(GlobalContextEntryRecord)
                        .where(GlobalContextEntryRecord.session_id == session_id)
                        .order_by(GlobalContextEntryRecord.sequence.desc())
                    )
                ).all()
            )

        matches: list[ContextSearchMatch] = []
        for record in records:
            score = lexical_score(query=query, content=record.content)
            if score <= 0:
                continue
            matches.append(
                ContextSearchMatch(
                    entry=_entry_from_record(record),
                    score=score,
                )
            )
        matches.sort(key=lambda match: (match.score, match.entry.sequence), reverse=True)
        return matches[:limit]


def _snapshot_from_record(record: ContextSnapshotRecord) -> ContextSnapshot:
    return ContextSnapshot(
        id=record.id,
        session_id=record.session_id,
        execution_id=record.execution_id,
        sequence=record.sequence,
        reason=SnapshotReason(record.reason),
        summary=ContextSummary.model_validate(record.summary_json),
        estimated_tokens=record.estimated_tokens,
        created_at=record.created_at,
    )


def _entry_from_record(record: GlobalContextEntryRecord) -> GlobalContextEntry:
    return GlobalContextEntry(
        id=record.id,
        session_id=record.session_id,
        execution_id=record.execution_id,
        sequence=record.sequence,
        kind=GlobalContextKind(record.kind),
        content=record.content,
        metadata=dict(record.metadata_json or {}),
        created_at=record.created_at,
    )
