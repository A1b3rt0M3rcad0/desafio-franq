from types import SimpleNamespace
from typing import Any

import pytest

from package.agent.llm.config import OpenAIConfig, ReasoningEffort
from package.agent.llm.models import LLMMessage, MessageRole
from package.agent.llm.providers.gpt import GPTLLM
from package.agent.llm.providers.openai import OpenAILLM


class FakeAsyncStream:
    def __init__(self, events: list[Any]) -> None:
        self._events = events
        self._index = 0
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._events):
            raise StopAsyncIteration
        event = self._events[self._index]
        self._index += 1
        return event

    async def close(self) -> None:
        self.closed = True


class FakeResponsesResource:
    def __init__(self, stream: FakeAsyncStream) -> None:
        self.stream = stream
        self.kwargs: dict[str, Any] | None = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return self.stream


class FakeCompletionsResource:
    def __init__(self, stream: FakeAsyncStream) -> None:
        self.stream = stream
        self.kwargs: dict[str, Any] | None = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return self.stream


class FakeOpenAIClient:
    def __init__(
        self,
        *,
        responses: FakeResponsesResource | None = None,
        completions: FakeCompletionsResource | None = None,
    ) -> None:
        self.responses = responses
        self.chat = SimpleNamespace(completions=completions)


def _config() -> OpenAIConfig:
    return OpenAIConfig(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="gpt-test",
        timeout_seconds=30.0,
        max_output_tokens=512,
        reasoning_effort=ReasoningEffort.MEDIUM,
        store=False,
    )


@pytest.mark.asyncio
async def test_openai_responses_streams_text_deltas() -> None:
    stream = FakeAsyncStream(
        [
            SimpleNamespace(type="response.created"),
            SimpleNamespace(type="response.output_text.delta", delta="Olá"),
            SimpleNamespace(type="response.output_text.delta", delta=" mundo"),
        ]
    )
    responses = FakeResponsesResource(stream)
    client = FakeOpenAIClient(responses=responses)
    llm = OpenAILLM(_config(), client=client)

    chunks = [
        chunk.content
        async for chunk in llm.stream(
            [LLMMessage(role=MessageRole.USER, content="Diga olá")]
        )
    ]

    assert chunks == ["Olá", " mundo"]
    assert stream.closed is True
    assert responses.kwargs is not None
    assert responses.kwargs["model"] == "gpt-test"
    assert responses.kwargs["stream"] is True
    assert responses.kwargs["store"] is False


@pytest.mark.asyncio
async def test_gpt_chat_streams_choice_deltas() -> None:
    stream = FakeAsyncStream(
        [
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="Olá"))]
            ),
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=" mundo"))]
            ),
        ]
    )
    completions = FakeCompletionsResource(stream)
    client = FakeOpenAIClient(completions=completions)
    llm = GPTLLM(_config(), client=client)

    chunks = [
        chunk.content
        async for chunk in llm.stream(
            [LLMMessage(role=MessageRole.USER, content="Diga olá")]
        )
    ]

    assert chunks == ["Olá", " mundo"]
    assert stream.closed is True
    assert completions.kwargs is not None
    assert completions.kwargs["model"] == "gpt-test"
    assert completions.kwargs["stream"] is True
    assert completions.kwargs["reasoning_effort"] == "medium"


@pytest.mark.asyncio
async def test_tool_message_requires_tool_call_id() -> None:
    stream = FakeAsyncStream([])
    responses = FakeResponsesResource(stream)
    client = FakeOpenAIClient(responses=responses)
    llm = OpenAILLM(_config(), client=client)

    with pytest.raises(ValueError, match="tool_call_id"):
        _ = [
            chunk.content
            async for chunk in llm.stream(
                [LLMMessage(role=MessageRole.TOOL, content="resultado")]
            )
        ]
