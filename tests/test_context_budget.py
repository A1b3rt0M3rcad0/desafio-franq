from package.agent.context.budget import (
    ApproximateTokenEstimator,
    ContextBudgetManager,
    ContextBudgetPolicy,
)
from package.agent.llm.models import LLMMessage, MessageRole


def _manager() -> ContextBudgetManager:
    return ContextBudgetManager(
        estimator=ApproximateTokenEstimator(chars_per_token=1.0),
        policy=ContextBudgetPolicy(
            model_context_window_tokens=1000,
            dynamic_context_percentage=25.0,
        ),
    )


def test_dynamic_budget_is_percentage_of_model_context_window() -> None:
    manager = _manager()
    report = manager.measure(
        mandatory_messages=[LLMMessage(role=MessageRole.SYSTEM, content="x" * 700)],
        dynamic_messages=[LLMMessage(role=MessageRole.USER, content="y" * 100)],
    )

    assert report.dynamic_budget_tokens == 250
    assert report.dynamic_tokens > 0
    assert report.dynamic_tokens <= report.dynamic_budget_tokens
    assert report.over_budget is False
    assert report.mandatory_tokens > report.dynamic_budget_tokens


def test_mandatory_context_does_not_consume_dynamic_budget() -> None:
    manager = _manager()
    small = manager.measure(
        mandatory_messages=[LLMMessage(role=MessageRole.SYSTEM, content="m" * 800)],
        dynamic_messages=[LLMMessage(role=MessageRole.USER, content="d" * 100)],
    )
    overflow = manager.measure(
        mandatory_messages=[LLMMessage(role=MessageRole.SYSTEM, content="m")],
        dynamic_messages=[LLMMessage(role=MessageRole.USER, content="d" * 400)],
    )

    assert small.over_budget is False
    assert overflow.over_budget is True


def test_invalid_budget_policy_is_rejected() -> None:
    for percentage in (0, -1, 101):
        try:
            ContextBudgetPolicy(
                model_context_window_tokens=1000,
                dynamic_context_percentage=percentage,
            )
        except ValueError:
            continue
        raise AssertionError("invalid context budget percentage was accepted")
