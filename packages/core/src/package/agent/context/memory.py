from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from package.agent.context.models import (
    ContextSearchMatch,
    ContextSnapshot,
    ContextSummary,
    GlobalContextEntry,
    GlobalContextKind,
    SnapshotReason,
)
from package.agent.context.retrieval import lexical_score


class InMemoryContextSnapshotStore:
    def __init__(self) -> None:
        self.snapshots: list[ContextSnapshot] = []

    async def latest(self, session_id: str) -> ContextSnapshot | None:
        matches = [snapshot for snapshot in self.snapshots if snapshot.session_id == session_id]
        if not matches:
            return None
        return max(matches, key=lambda snapshot: snapshot.sequence)

    async def create(
        self,
        *,
        session_id: str,
        execution_id: str,
        reason: SnapshotReason,
        summary: ContextSummary,
        estimated_tokens: int,
    ) -> ContextSnapshot:
        previous = await self.latest(session_id)
        snapshot = ContextSnapshot(
            id=str(uuid4()),
            session_id=session_id,
            execution_id=execution_id,
            sequence=1 if previous is None else previous.sequence + 1,
            reason=reason,
            summary=summary,
            estimated_tokens=estimated_tokens,
            created_at=datetime.now(timezone.utc),
        )
        self.snapshots.append(snapshot)
        return snapshot


class InMemoryGlobalContextStore:
    def __init__(self) -> None:
        self.entries: list[GlobalContextEntry] = []

    async def append(
        self,
        *,
        session_id: str,
        execution_id: str,
        kind: GlobalContextKind,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> GlobalContextEntry:
        sequence = 1 + max(
            (
                entry.sequence
                for entry in self.entries
                if entry.session_id == session_id
            ),
            default=0,
        )
        entry = GlobalContextEntry(
            id=str(uuid4()),
            session_id=session_id,
            execution_id=execution_id,
            sequence=sequence,
            kind=kind,
            content=content,
            metadata=metadata or {},
            created_at=datetime.now(timezone.utc),
        )
        self.entries.append(entry)
        return entry

    async def search(
        self,
        *,
        session_id: str,
        query: str,
        limit: int,
    ) -> list[ContextSearchMatch]:
        scored: list[ContextSearchMatch] = []
        for entry in self.entries:
            if entry.session_id != session_id:
                continue
            score = lexical_score(query=query, content=entry.content)
            if score <= 0:
                continue
            scored.append(ContextSearchMatch(entry=entry, score=score))
        scored.sort(key=lambda match: (match.score, match.entry.sequence), reverse=True)
        return scored[:limit]
