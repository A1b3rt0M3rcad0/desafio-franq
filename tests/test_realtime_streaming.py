from collections.abc import AsyncIterator
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessageChunk

from package.agent.llm.config import OpenAIConfig, ReasoningEffort
from package.agent.llm.models import LLMMessage, LLMToolDefinition, MessageRole
from package.agent.llm.providers.openai import OpenAILLM
from package.agent.llm.realtime import bind_text_delta_handler, current_text_delta_handler
from package.agent.observer.events import ExecutionEvent, ExecutionEventType
from package.agent.runtime.streaming import RuntimeStreamingEventSink


class StreamingToolFakeChatModel(GenericFakeChatModel):
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
async def test_tool_aware_invoke_streams_provider_text_deltas() -> None:
    model = StreamingToolFakeChatModel(messages=iter(["unused"]))
    llm = OpenAILLM(_openai_config(), model=model)
    deltas: list[str] = []

    async def on_delta(content: str) -> None:
        deltas.append(content)

    with bind_text_delta_handler(on_delta):
        response = await llm.invoke(
            [LLMMessage(role=MessageRole.USER, content="Diga olá")],
            tools=[_tool_definition()],
        )

    assert response.content == "Olá mundo"
    assert deltas == ["Olá ", "mundo"]
    assert current_text_delta_handler() is None


class CapturingSink:
    def __init__(self) -> None:
        self.events: list[ExecutionEvent] = []

    async def emit(self, event: ExecutionEvent) -> None:
        self.events.append(event)


@pytest.mark.asyncio
async def test_runtime_streaming_sink_suppresses_legacy_full_answer_duplicate() -> None:
    delegate = CapturingSink()
    sink = RuntimeStreamingEventSink(
        delegate=delegate,
        execution_id="execution-1",
    )

    await sink.emit_model_delta("Olá ")
    await sink.emit_model_delta("mundo")
    await sink.emit(
        ExecutionEvent(
            execution_id="execution-1",
            type=ExecutionEventType.AGENT_DECISION,
            payload={"decision": "answer"},
        )
    )
    await sink.emit(
        ExecutionEvent(
            execution_id="execution-1",
            type=ExecutionEventType.ASSISTANT_DELTA,
            payload={"content": "Olá mundo"},
        )
    )

    deltas = [
        event.payload["content"]
        for event in delegate.events
        if event.type == ExecutionEventType.ASSISTANT_DELTA
    ]
    assert deltas == ["Olá ", "mundo"]


@pytest.mark.asyncio
async def test_runtime_streaming_sink_resets_deduplication_after_tool_action() -> None:
    delegate = CapturingSink()
    sink = RuntimeStreamingEventSink(
        delegate=delegate,
        execution_id="execution-1",
    )

    await sink.emit_model_delta("Vou consultar.")
    await sink.emit(
        ExecutionEvent(
            execution_id="execution-1",
            type=ExecutionEventType.AGENT_DECISION,
            payload={"decision": "action"},
        )
    )
    await sink.emit(
        ExecutionEvent(
            execution_id="execution-1",
            type=ExecutionEventType.ASSISTANT_DELTA,
            payload={"content": "Resposta final"},
        )
    )

    deltas = [
        event.payload["content"]
        for event in delegate.events
        if event.type == ExecutionEventType.ASSISTANT_DELTA
    ]
    assert deltas == ["Vou consultar.", "Resposta final"]
