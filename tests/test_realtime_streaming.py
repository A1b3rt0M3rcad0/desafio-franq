from collections.abc import AsyncIterator
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessageChunk

from package.agent.llm.config import OpenAIConfig, ReasoningEffort
from package.agent.llm.models import LLMMessage, LLMToolDefinition, MessageRole
from package.agent.llm.providers.openai import OpenAILLM
from package.agent.llm.realtime import bind_text_delta_handler


class StreamingToolFakeChatModel(GenericFakeChatModel):
    def __init__(self) -> None:
        super().__init__(messages=iter(["decisão sem streaming"]))
        self.stream_calls = 0

    def bind_tools(self, tools, **kwargs):
        del tools, kwargs
        return self

    async def astream(
        self,
        input: Any,
        config: Any = None,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[AIMessageChunk]:
        del input, config, stop, kwargs
        self.stream_calls += 1
        yield AIMessageChunk(content="Olá ")
        yield AIMessageChunk(content="mundo")


def _openai_config() -> OpenAIConfig:
    return OpenAIConfig(
        api_key="test-key",
        base_url="https://api.openai.test/v1",
        model="gpt-test",
        timeout_seconds=30.0,
        max_output_tokens=512,
        max_retries=2,
        reasoning_effort=ReasoningEffort.MEDIUM,
        store=False,
    )


def _tool_definition() -> LLMToolDefinition:
    return LLMToolDefinition(
        name="database",
        description="Consulta dados",
        input_schema={"type": "object", "properties": {}},
    )


@pytest.mark.asyncio
async def test_tool_aware_invoke_never_exposes_reasoning_text_as_public_deltas() -> None:
    model = StreamingToolFakeChatModel()
    llm = OpenAILLM(_openai_config(), model=model)
    deltas: list[str] = []

    async def on_delta(content: str) -> None:
        deltas.append(content)

    with bind_text_delta_handler(on_delta):
        response = await llm.invoke(
            [LLMMessage(role=MessageRole.USER, content="Diga olá")],
            tools=[_tool_definition()],
        )

    assert response.content == "decisão sem streaming"
    assert deltas == []
    assert model.stream_calls == 0


@pytest.mark.asyncio
async def test_explicit_final_answer_stream_yields_provider_chunks() -> None:
    model = StreamingToolFakeChatModel()
    llm = OpenAILLM(_openai_config(), model=model)

    chunks = [
        chunk.content
        async for chunk in llm.stream(
            [LLMMessage(role=MessageRole.USER, content="Diga olá")]
        )
    ]

    assert chunks == ["Olá ", "mundo"]
    assert model.stream_calls == 1
