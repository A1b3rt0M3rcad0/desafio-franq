from collections.abc import Sequence
from typing import Any, Protocol

from package.agent.context.models import (
    ContextSearchMatch,
    ContextSnapshot,
    ContextSummary,
    GlobalContextEntry,
    GlobalContextKind,
    SnapshotReason,
)
from package.agent.llm.models import LLMMessage, LLMToolDefinition


class TokenEstimator(Protocol):
    def estimate_text(self, text: str) -> int: ...

    def estimate_messages(self, messages: Sequence[LLMMessage]) -> int: ...

    def estimate_tool_definitions(self, tools: Sequence[LLMToolDefinition]) -> int: ...


class ContextSummarizer(Protocol):
    async def summarize(
        self,
        *,
        previous_snapshot: ContextSnapshot | None,
        messages: Sequence[LLMMessage],
        question: str,
    ) -> ContextSummary: ...


class ContextSnapshotStore(Protocol):
    async def latest(self, session_id: str) -> ContextSnapshot | None: ...

    async def create(
        self,
        *,
        session_id: str,
        execution_id: str,
        reason: SnapshotReason,
        summary: ContextSummary,
        estimated_tokens: int,
    ) -> ContextSnapshot: ...


class GlobalContextStore(Protocol):
    async def append(
        self,
        *,
        session_id: str,
        execution_id: str,
        kind: GlobalContextKind,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> GlobalContextEntry: ...

    async def search(
        self,
        *,
        session_id: str,
        query: str,
        limit: int,
    ) -> list[ContextSearchMatch]: ...
