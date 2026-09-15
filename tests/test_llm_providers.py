import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import ToolMessage

from package.agent.llm.config import DeepSeekConfig, OpenAIConfig, ReasoningEffort
from package.agent.llm.models import (
    LLMMessage,
    LLMToolCall,
    LLMToolDefinition,
    MessageRole,
)
from package.agent.llm.providers._messages import to_langchain_messages
from package.agent.llm.providers.deepseek import DeepSeekLLM
from package.agent.llm.providers.openai import OpenAILLM


class CountingFakeChatModel(GenericFakeChatModel):
    def get_num_tokens(self, text: str) -> int:
        return len(text.split())

    def get_num_tokens_from_messages(self, messages, tools=None, **kwargs) -> int:
        del tools, kwargs
        return sum(len(str(message.content).split()) + 1 for message in messages)


class UnsupportedMessageCountingModel(CountingFakeChatModel):
    def get_num_tokens_from_messages(self, messages, tools=None, **kwargs) -> int:
        del messages, tools, kwargs
        raise NotImplementedError(
            "get_num_tokens_from_messages() is not presently implemented for model deepseek-flash"
        )


class CountingTokenizer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def encode(self, text: str, *, add_special_tokens: bool = True) -> list[int]:
        self.calls.append((text, add_special_tokens))
        return list(range(len(text)))


class FailingTokenizer:
    def encode(self, text: str, *, add_special_tokens: bool = True) -> list[int]:
        del text, add_special_tokens
        raise ValueError("tokenizer unavailable")


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


def _deepseek_config(model: str = "deepseek-test") -> DeepSeekConfig:
    return DeepSeekConfig(
        api_key="test-key",
        base_url="https://api.deepseek.test/v1",
        model=model,
        timeout_seconds=30.0,
        max_output_tokens=512,
        max_retries=2,
        reasoning_effort=ReasoningEffort.HIGH,
    )


@pytest.mark.asyncio
async def test_openai_streams_through_langchain_adapter() -> None:
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
async def test_deepseek_streams_through_langchain_adapter() -> None:
    model = GenericFakeChatModel(messages=iter(["Olá DeepSeek"]))
    llm = DeepSeekLLM(_deepseek_config(), model=model, tokenizer=CountingTokenizer())

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


def test_llm_profile_comes_from_active_model_profile() -> None:
    model = CountingFakeChatModel(
        messages=iter(["unused"]),
        profile={"max_input_tokens": 123_456},
    )
    llm = OpenAILLM(_openai_config(), model=model)

    assert llm.profile.provider == "openai"
    assert llm.profile.model == "gpt-test"
    assert llm.profile.context_window_tokens == 123_456


def test_deepseek_profile_prefers_langchain_model_profile() -> None:
    model = CountingFakeChatModel(
        messages=iter(["unused"]),
        profile={"max_input_tokens": 321_000},
    )
    llm = DeepSeekLLM(
        _deepseek_config("deepseek-flash"),
        model=model,
        tokenizer=CountingTokenizer(),
    )

    assert llm.profile.provider == "deepseek"
    assert llm.profile.model == "deepseek-flash"
    assert llm.profile.context_window_tokens == 321_000


def test_deepseek_profile_uses_provider_fallback_when_adapter_has_no_profile() -> None:
    model = GenericFakeChatModel(messages=iter(["unused"]))
    llm = DeepSeekLLM(
        _deepseek_config("deepseek-flash"),
        model=model,
        tokenizer=CountingTokenizer(),
    )

    assert llm.profile.provider == "deepseek"
    assert llm.profile.model == "deepseek-flash"
    assert llm.profile.context_window_tokens == 1_000_000


def test_deepseek_unknown_model_without_profile_still_fails_fast() -> None:
    model = GenericFakeChatModel(messages=iter(["unused"]))
    llm = DeepSeekLLM(
        _deepseek_config("deepseek-unknown"),
        model=model,
        tokenizer=CountingTokenizer(),
    )

    with pytest.raises(RuntimeError, match="max_input_tokens"):
        _ = llm.profile


def test_llm_token_count_is_delegated_to_model_tokenizer() -> None:
    model = CountingFakeChatModel(
        messages=iter(["unused"]),
        profile={"max_input_tokens": 123_456},
    )
    llm = OpenAILLM(_openai_config(), model=model)
    messages = [LLMMessage(role=MessageRole.USER, content="um dois três")]
    tools = [
        LLMToolDefinition(
            name="lookup",
            description="consulta valor",
            input_schema={"type": "object", "properties": {}},
        )
    ]

    assert llm.count_text_tokens("um dois três") == 3
    assert llm.count_tokens(messages) == 4
    assert llm.count_tokens(messages, tools=tools) > 4


def test_deepseek_token_count_does_not_use_unsupported_langchain_message_counter() -> None:
    model = UnsupportedMessageCountingModel(
        messages=iter(["unused"]),
        profile={"max_input_tokens": 1_000_000},
    )
    tokenizer = CountingTokenizer()
    llm = DeepSeekLLM(
        _deepseek_config("deepseek-flash"),
        model=model,
        tokenizer=tokenizer,
    )
    messages = [LLMMessage(role=MessageRole.USER, content="analise os dados")]

    token_count = llm.count_tokens(messages)

    assert token_count > 0
    assert tokenizer.calls
    assert tokenizer.calls[-1][1] is False


def test_deepseek_token_count_includes_tools_and_native_tool_calls() -> None:
    tokenizer = CountingTokenizer()
    model = UnsupportedMessageCountingModel(
        messages=iter(["unused"]),
        profile={"max_input_tokens": 1_000_000},
    )
    llm = DeepSeekLLM(
        _deepseek_config("deepseek-flash"),
        model=model,
        tokenizer=tokenizer,
    )
    plain_messages = [LLMMessage(role=MessageRole.USER, content="consulta")]
    tool_messages = [
        *plain_messages,
        LLMMessage(
            role=MessageRole.ASSISTANT,
            content="",
            tool_calls=(
                LLMToolCall(
                    id="call-1",
                    name="database",
                    arguments={"action": "query", "sql": "SELECT 1"},
                ),
            ),
        ),
    ]
    tools = [
        LLMToolDefinition(
            name="database",
            description="Consulta o banco",
            input_schema={"type": "object", "properties": {"sql": {"type": "string"}}},
        )
    ]

    plain_count = llm.count_tokens(plain_messages)
    tool_count = llm.count_tokens(tool_messages, tools=tools)

    assert tool_count > plain_count


def test_deepseek_empty_token_inputs_do_not_call_tokenizer() -> None:
    tokenizer = FailingTokenizer()
    model = UnsupportedMessageCountingModel(
        messages=iter(["unused"]),
        profile={"max_input_tokens": 1_000_000},
    )
    llm = DeepSeekLLM(
        _deepseek_config("deepseek-flash"),
        model=model,
        tokenizer=tokenizer,
    )

    assert llm.count_text_tokens("") == 0
    assert llm.count_tokens(()) == 0


def test_deepseek_tokenizer_failure_is_explicit_and_model_scoped() -> None:
    model = UnsupportedMessageCountingModel(
        messages=iter(["unused"]),
        profile={"max_input_tokens": 1_000_000},
    )
    llm = DeepSeekLLM(
        _deepseek_config("deepseek-flash"),
        model=model,
        tokenizer=FailingTokenizer(),
    )

    with pytest.raises(RuntimeError, match="DeepSeek tokenizer failed.*deepseek-flash"):
        llm.count_tokens([LLMMessage(role=MessageRole.USER, content="teste")])


def test_missing_model_context_profile_fails_fast() -> None:
    model = GenericFakeChatModel(messages=iter(["unused"]))
    llm = OpenAILLM(_openai_config(), model=model)

    with pytest.raises(RuntimeError, match="max_input_tokens"):
        _ = llm.profile
