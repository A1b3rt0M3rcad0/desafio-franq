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
    tool_call_count: int
    answer: str
    stop_reason: str | None
    observer: ExecutionObserver
    metadata: dict[str, Any]
