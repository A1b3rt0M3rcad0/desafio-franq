import json
import math
from collections.abc import Sequence
from dataclasses import dataclass

from package.agent.context.contracts import TokenEstimator
from package.agent.context.models import ContextBudgetReport
from package.agent.llm.models import LLMMessage, LLMToolDefinition


@dataclass(frozen=True, slots=True)
class ContextBudgetPolicy:
    model_context_window_tokens: int
    dynamic_context_percentage: float

    def __post_init__(self) -> None:
        if self.model_context_window_tokens < 1:
            raise ValueError("model_context_window_tokens must be greater than zero")
        if not 0 < self.dynamic_context_percentage <= 100:
            raise ValueError("dynamic_context_percentage must be between 0 and 100")

    @property
    def dynamic_budget_tokens(self) -> int:
        return max(
            1,
            int(self.model_context_window_tokens * self.dynamic_context_percentage / 100),
        )


class ApproximateTokenEstimator(TokenEstimator):
    """Provider-independent fallback estimator.

    The ratio is external configuration so a provider-specific estimator can replace
    this implementation later without changing the Context Manager contract.
    """

    def __init__(self, *, chars_per_token: float) -> None:
        if chars_per_token <= 0:
            raise ValueError("chars_per_token must be greater than zero")
        self._chars_per_token = chars_per_token

    def estimate_text(self, text: str) -> int:
        if not text:
            return 0
        return max(1, math.ceil(len(text) / self._chars_per_token))

    def estimate_messages(self, messages: Sequence[LLMMessage]) -> int:
        total = 0
        for message in messages:
            payload = {
                "role": message.role.value,
                "content": message.content,
                "tool_call_id": message.tool_call_id,
                "tool_calls": [call.model_dump(mode="json") for call in message.tool_calls],
            }
            total += self.estimate_text(json.dumps(payload, ensure_ascii=False))
        return total

    def estimate_tool_definitions(self, tools: Sequence[LLMToolDefinition]) -> int:
        if not tools:
            return 0
        payload = [tool.model_dump(mode="json") for tool in tools]
        return self.estimate_text(json.dumps(payload, ensure_ascii=False))


class ContextBudgetManager:
    def __init__(
        self,
        *,
        estimator: TokenEstimator,
        policy: ContextBudgetPolicy,
    ) -> None:
        self._estimator = estimator
        self._policy = policy

    @property
    def estimator(self) -> TokenEstimator:
        return self._estimator

    @property
    def policy(self) -> ContextBudgetPolicy:
        return self._policy

    def measure(
        self,
        *,
        mandatory_messages: Sequence[LLMMessage],
        dynamic_messages: Sequence[LLMMessage],
        tool_definitions: Sequence[LLMToolDefinition] = (),
    ) -> ContextBudgetReport:
        mandatory_tokens = self._estimator.estimate_messages(mandatory_messages)
        mandatory_tokens += self._estimator.estimate_tool_definitions(tool_definitions)
        dynamic_tokens = self._estimator.estimate_messages(dynamic_messages)
        dynamic_budget_tokens = self._policy.dynamic_budget_tokens
        usage = (dynamic_tokens / dynamic_budget_tokens * 100) if dynamic_budget_tokens else 0.0
        return ContextBudgetReport(
            model_context_window_tokens=self._policy.model_context_window_tokens,
            dynamic_budget_tokens=dynamic_budget_tokens,
            mandatory_tokens=mandatory_tokens,
            dynamic_tokens=dynamic_tokens,
            total_estimated_tokens=mandatory_tokens + dynamic_tokens,
            dynamic_usage_percentage=round(usage, 2),
            over_budget=dynamic_tokens > dynamic_budget_tokens,
        )
