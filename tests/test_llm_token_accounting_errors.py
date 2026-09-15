import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

from package.agent.llm.config import OpenAIConfig, ReasoningEffort
from package.agent.llm.models import LLMMessage, LLMToolDefinition, MessageRole
from package.agent.llm.providers.openai import OpenAILLM


class UnsupportedCounterModel(GenericFakeChatModel):
    def get_num_tokens(self, text: str) -> int:
        return len(text)

    def get_num_tokens_from_messages(self, messages, tools=None, **kwargs) -> int:
        del messages, tools, kwargs
        raise NotImplementedError("message token counting not implemented")


class UnsupportedCounterValueErrorModel(GenericFakeChatModel):
    def get_num_tokens(self, text: str) -> int:
        return len(text)

    def get_num_tokens_from_messages(self, messages, tools=None, **kwargs) -> int:
        del messages, tools, kwargs
        raise ValueError(
            "get_num_tokens_from_messages() is not presently implemented for model custom-model"
        )


class BrokenMessageCounterModel(GenericFakeChatModel):
    def get_num_tokens(self, text: str) -> int:
        return len(text)

    def get_num_tokens_from_messages(self, messages, tools=None, **kwargs) -> int:
        del messages, tools, kwargs
        raise ValueError("malformed messages")


class BrokenTextCounterModel(GenericFakeChatModel):
    def get_num_tokens(self, text: str) -> int:
        del text
        raise RuntimeError("tokenizer crashed")

    def get_num_tokens_from_messages(self, messages, tools=None, **kwargs) -> int:
        del messages, tools, kwargs
        raise NotImplementedError("unsupported")


def _config() -> OpenAIConfig:
    return OpenAIConfig(
        api_key="test-key",
        base_url="https://api.openai.test/v1",
        model="custom-model",
        timeout_seconds=30.0,
        max_output_tokens=512,
        max_retries=2,
        reasoning_effort=ReasoningEffort.MEDIUM,
        store=False,
    )


def test_not_implemented_message_counter_falls_back_to_text_tokenizer() -> None:
    llm = OpenAILLM(
        _config(),
        model=UnsupportedCounterModel(
            messages=iter(["unused"]),
            profile={"max_input_tokens": 10_000},
        ),
    )

    count = llm.count_tokens([LLMMessage(role=MessageRole.USER, content="olá")])

    assert count > len("olá")


def test_known_unsupported_value_error_falls_back_to_text_tokenizer() -> None:
    llm = OpenAILLM(
        _config(),
        model=UnsupportedCounterValueErrorModel(
            messages=iter(["unused"]),
            profile={"max_input_tokens": 10_000},
        ),
    )

    count = llm.count_tokens([LLMMessage(role=MessageRole.USER, content="olá")])

    assert count > 0


def test_unrelated_message_counter_value_error_is_not_swallowed() -> None:
    llm = OpenAILLM(
        _config(),
        model=BrokenMessageCounterModel(
            messages=iter(["unused"]),
            profile={"max_input_tokens": 10_000},
        ),
    )

    with pytest.raises(ValueError, match="malformed messages"):
        llm.count_tokens([LLMMessage(role=MessageRole.USER, content="olá")])


def test_fallback_tokenizer_failure_is_propagated_instead_of_returning_fake_count() -> None:
    llm = OpenAILLM(
        _config(),
        model=BrokenTextCounterModel(
            messages=iter(["unused"]),
            profile={"max_input_tokens": 10_000},
        ),
    )

    with pytest.raises(RuntimeError, match="tokenizer crashed"):
        llm.count_tokens([LLMMessage(role=MessageRole.USER, content="olá")])


def test_empty_context_does_not_invoke_message_counter() -> None:
    llm = OpenAILLM(
        _config(),
        model=BrokenMessageCounterModel(
            messages=iter(["unused"]),
            profile={"max_input_tokens": 10_000},
        ),
    )

    assert llm.count_tokens(()) == 0


def test_tool_schema_is_counted_even_without_messages() -> None:
    llm = OpenAILLM(
        _config(),
        model=UnsupportedCounterModel(
            messages=iter(["unused"]),
            profile={"max_input_tokens": 10_000},
        ),
    )
    tool = LLMToolDefinition(
        name="database",
        description="Consulta o banco",
        input_schema={"type": "object", "properties": {"sql": {"type": "string"}}},
    )

    assert llm.count_tokens((), tools=[tool]) > 0
