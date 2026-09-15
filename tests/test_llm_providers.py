import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import ToolMessage

from package.agent.llm.config import DeepSeekConfig, OpenAIConfig, ReasoningEffort
from package.agent.llm.models import LLMMessage, MessageRole
from package.agent.llm.providers._messages import to_langchain_messages
from package.agent.llm.providers.deepseek import DeepSeekLLM
from package.agent.llm.providers.openai import OpenAILLM


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


def _deepseek_config() -> DeepSeekConfig:
    return DeepSeekConfig(
        api_key="test-key",
        base_url="https://api.deepseek.test/v1",
        model="deepseek-test",
        timeout_seconds=30.0,
        max_output_tokens=512,
        max_retries=2,
        reasoning_effort=ReasoningEffort.HIGH,
    )


@pytest.mark.asyncio
async def test_openai_streams_through_langgraph() -> None:
    model = GenericFakeChatModel(messages=iter(["Olá mundo"]))
    llm = OpenAILLM(_openai_config(), model=model)

    chunks = [
        chunk.content
        async for chunk in llm.stream(
            [LLMMessage(role=MessageRole.USER, content="Diga olá")]
        )
    ]

    assert "".join(chunks) == "Olá mundo"


@pytest.mark.asyncio
async def test_deepseek_streams_through_langgraph() -> None:
    model = GenericFakeChatModel(messages=iter(["Olá DeepSeek"]))
    llm = DeepSeekLLM(_deepseek_config(), model=model)

    chunks = [
        chunk.content
        async for chunk in llm.stream(
            [LLMMessage(role=MessageRole.USER, content="Diga olá")]
        )
    ]

    assert "".join(chunks) == "Olá DeepSeek"


@pytest.mark.asyncio
async def test_llm_requires_at_least_one_message() -> None:
    model = GenericFakeChatModel(messages=iter(["unused"]))
    llm = OpenAILLM(_openai_config(), model=model)

    with pytest.raises(ValueError, match="At least one LLM message"):
        _ = [chunk async for chunk in llm.stream([])]


def test_tool_message_requires_tool_call_id() -> None:
    with pytest.raises(ValueError, match="tool_call_id"):
        to_langchain_messages(
            [LLMMessage(role=MessageRole.TOOL, content="resultado")]
        )


def test_tool_message_is_converted_to_langchain_tool_message() -> None:
    messages = to_langchain_messages(
        [
            LLMMessage(
                role=MessageRole.TOOL,
                content="resultado",
                tool_call_id="call-1",
            )
        ]
    )

    assert len(messages) == 1
    assert isinstance(messages[0], ToolMessage)
    assert messages[0].tool_call_id == "call-1"
