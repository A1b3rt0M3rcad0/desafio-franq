from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

from package.agent.context.budget import (
    ContextBudgetManager,
    ContextBudgetPolicy,
    ModelTokenEstimator,
)
from package.agent.llm.config import DeepSeekConfig, ReasoningEffort
from package.agent.llm.models import LLMMessage, LLMToolDefinition, MessageRole
from package.agent.llm.providers.deepseek import DeepSeekLLM


class DeepSeekLikeModelWithoutLangChainMessageCounter(GenericFakeChatModel):
    def get_num_tokens_from_messages(self, messages, tools=None, **kwargs) -> int:
        del messages, tools, kwargs
        raise NotImplementedError(
            "get_num_tokens_from_messages() is not presently implemented for model deepseek-flash"
        )

    def get_num_tokens(self, text: str) -> int:
        del text
        raise AssertionError(
            "DeepSeek runtime accounting must use the DeepSeek tokenizer, not LangChain"
        )


def _config() -> DeepSeekConfig:
    return DeepSeekConfig(
        api_key="test-key",
        base_url="https://api.deepseek.test/v1",
        model="deepseek-flash",
        timeout_seconds=30.0,
        max_output_tokens=4096,
        max_retries=2,
        reasoning_effort=ReasoningEffort.HIGH,
    )


def test_deepseek_context_budget_uses_provider_tokenizer_end_to_end() -> None:
    llm = DeepSeekLLM(
        _config(),
        model=DeepSeekLikeModelWithoutLangChainMessageCounter(
            messages=iter(["unused"]),
            profile=None,
        ),
    )
    estimator = ModelTokenEstimator(llm=llm)
    manager = ContextBudgetManager(
        estimator=estimator,
        policy=ContextBudgetPolicy(
            model_context_window_tokens=llm.profile.context_window_tokens,
            dynamic_context_percentage=25.0,
        ),
    )
    tools = [
        LLMToolDefinition(
            name="database",
            description="Consulta o banco SQLite",
            input_schema={
                "type": "object",
                "properties": {"sql": {"type": "string"}},
            },
        )
    ]

    report = manager.measure(
        mandatory_messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="Você é um analista de dados.")
        ],
        dynamic_messages=[
            LLMMessage(role=MessageRole.USER, content="Quais estados têm mais clientes?")
        ],
        tool_definitions=tools,
    )

    assert report.model_context_window_tokens == 1_000_000
    assert report.dynamic_budget_tokens == 250_000
    assert report.mandatory_tokens > 0
    assert report.dynamic_tokens > 0
    assert report.total_estimated_tokens == report.mandatory_tokens + report.dynamic_tokens
    assert report.over_budget is False
