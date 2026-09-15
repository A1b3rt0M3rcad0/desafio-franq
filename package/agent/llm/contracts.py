from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from package.agent.llm.models import (
    LLMChunk,
    LLMMessage,
    LLMResponse,
    LLMToolDefinition,
)


class LLMClient(Protocol):
    async def invoke(
        self,
        messages: Sequence[LLMMessage],
        *,
        tools: Sequence[LLMToolDefinition] = (),
    ) -> LLMResponse: ...

    async def stream(self, messages: Sequence[LLMMessage]) -> AsyncIterator[LLMChunk]: ...
