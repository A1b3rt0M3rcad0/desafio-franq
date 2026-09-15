from typing import Any, Protocol

from package.agent.observer.contracts import ExecutionEventSink
from package.agent.runtime.loop import RuntimePolicy


class AgentProgramResult(Protocol):
    answer: str
    result: dict[str, Any] | None


class AgentProgram(Protocol):
    async def execute(
        self,
        *,
        execution_id: str,
        session_id: str,
        question: str,
        observer: ExecutionEventSink,
        policy: RuntimePolicy,
    ) -> AgentProgramResult: ...
