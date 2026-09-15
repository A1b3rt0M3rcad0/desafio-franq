from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from package.agent.llm.models import (
    LLMChunk,
    LLMMessage,
    LLMModelProfile,
    LLMResponse,
    LLMToolDefinition,
)


class LLMClient(Protocol):
    @property
    def profile(self) -> LLMModelProfile: ...

    def count_text_tokens(self, text: str) -> int: ...

    def count_tokens(
        self,
        messages: Sequence[LLMMessage],
        *,
        tools: Sequence[LLMToolDefinition] = (),
    ) -> int: ...

    async def invoke(
        self,
        messages: Sequence[LLMMessage],
        *,
        tools: Sequence[LLMToolDefinition] = (),
    ) -> LLMResponse: ...

    async def stream(self, messages: Sequence[LLMMessage]) -> AsyncIterator[LLMChunk]: ...
