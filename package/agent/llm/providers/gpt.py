from collections.abc import AsyncIterator, Sequence

from openai import AsyncOpenAI

from package.agent.llm.config import OpenAIConfig
from package.agent.llm.contracts import LLMClient
from package.agent.llm.models import LLMChunk, LLMMessage
from package.agent.llm.providers._messages import to_chat_messages


class GPTLLM(LLMClient):
    """GPT implementation backed by the OpenAI Chat Completions API."""

    def __init__(
        self,
        config: OpenAIConfig,
        *,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._config = config
        self._client = client or AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout_seconds,
        )

    async def stream(self, messages: Sequence[LLMMessage]) -> AsyncIterator[LLMChunk]:
        normalized_messages = list(messages)
        if not normalized_messages:
            raise ValueError("At least one LLM message is required")

        completion_stream = await self._client.chat.completions.create(
            model=self._config.model,
            messages=to_chat_messages(normalized_messages),
            max_completion_tokens=self._config.max_output_tokens,
            reasoning_effort=self._config.reasoning_effort.value,
            store=self._config.store,
            stream=True,
        )

        try:
            async for chunk in completion_stream:
                for choice in chunk.choices:
                    if choice.delta.content:
                        yield LLMChunk(content=choice.delta.content)
        finally:
            await completion_stream.close()
