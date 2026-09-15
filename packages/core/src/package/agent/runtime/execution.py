from dataclasses import dataclass
from typing import Any

from package.agent.observer.contracts import ExecutionEventSink
from package.agent.runtime.contracts import AgentProgram
from package.agent.runtime.loop import RuntimePolicy


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    answer: str
    result: dict[str, Any] | None = None


class AgentRuntime:
    """Executes the Agent program while the Runner owns durable lifecycle transitions."""

    def __init__(
        self,
        *,
        program: AgentProgram,
        event_sink: ExecutionEventSink,
        policy: RuntimePolicy,
    ) -> None:
        self._program = program
        self._event_sink = event_sink
        self._policy = policy

    async def run(
        self,
        *,
        execution_id: str,
        session_id: str,
        question: str,
    ) -> RuntimeResult:
        program_result = await self._program.execute(
            execution_id=execution_id,
            session_id=session_id,
            question=question,
            observer=self._event_sink,
            policy=self._policy,
        )
        return RuntimeResult(
            answer=program_result.answer,
            result=program_result.result,
        )
