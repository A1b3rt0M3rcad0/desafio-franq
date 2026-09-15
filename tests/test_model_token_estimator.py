from collections.abc import AsyncIterator, Sequence

from package.agent.context.budget import ModelTokenEstimator
from package.agent.llm.models import (
    LLMChunk,
    LLMMessage,
    LLMModelProfile,
    LLMResponse,
    LLMToolDefinition,
    MessageRole,
)


class FakeModelLLM:
    @property
    def profile(self) -> LLMModelProfile:
        return LLMModelProfile(
            provider="fake",
            model="fake-model",
            context_window_tokens=1_000_000,
        )

    def count_text_tokens(self, text: str) -> int:
        return len(text)

    def count_tokens(
        self,
        messages: Sequence[LLMMessage],
        *,
        tools: Sequence[LLMToolDefinition] = (),
    ) -> int:
        return sum(len(message.content) for message in messages) + len(tools) * 10

    async def invoke(
        self,
        messages: Sequence[LLMMessage],
        *,
        tools: Sequence[LLMToolDefinition] = (),
    ) -> LLMResponse:
        raise NotImplementedError

    async def stream(self, messages: Sequence[LLMMessage]) -> AsyncIterator[LLMChunk]:
        if False:
            yield LLMChunk(content="")


def test_model_token_estimator_delegates_to_active_llm() -> None:
    estimator = ModelTokenEstimator(llm=FakeModelLLM())
    messages = [LLMMessage(role=MessageRole.USER, content="12345")]
    tools = [
        LLMToolDefinition(
            name="tool",
            description="tool",
            input_schema={"type": "object"},
        )
    ]

    assert estimator.estimate_text("abcd") == 4
    assert estimator.estimate_messages(messages) == 5
    assert estimator.estimate_tool_definitions(tools) == 10
