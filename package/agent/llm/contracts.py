from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from package.agent.llm.models import LLMChunk, LLMMessage


class LLMClient(Protocol):
    async def stream(self, messages: Sequence[LLMMessage]) -> AsyncIterator[LLMChunk]: ...
