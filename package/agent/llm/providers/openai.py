from collections.abc import AsyncIterator, Sequence

from openai import AsyncOpenAI

from package.agent.llm.config import OpenAIConfig
from package.agent.llm.contracts import LLMClient
from package.agent.llm.models import LLMChunk, LLMMessage
from package.agent.llm.providers._messages import to_responses_input


class OpenAILLM(LLMClient):
    """OpenAI implementation backed by the Responses API."""

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

        response_stream = await self._client.responses.create(
            model=self._config.model,
            input=to_responses_input(normalized_messages),
            max_output_tokens=self._config.max_output_tokens,
            reasoning={"effort": self._config.reasoning_effort.value},
            store=self._config.store,
            stream=True,
        )

        try:
            async for event in response_stream:
                if event.type != "response.output_text.delta":
                    continue
                if event.delta:
                    yield LLMChunk(content=event.delta)
        finally:
            await response_stream.close()
