from typing import Any, TypedDict

from package.agent.llm.models import LLMMessage, LLMToolCall
from package.agent.observer.contracts import ExecutionObserver


class AgentGraphState(TypedDict):
    execution_id: str
    session_id: str
    question: str
    messages: list[LLMMessage]
    iteration: int
    max_iterations: int
    pending_tool_calls: list[LLMToolCall]
    active_skill_names: list[str]
    tool_call_count: int
    skill_use_count: int
    max_parallel_tool_calls_per_tool: int
    answer: str
    stop_reason: str | None
    observer: ExecutionObserver
    metadata: dict[str, Any]
