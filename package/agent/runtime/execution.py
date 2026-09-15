from dataclasses import dataclass
from typing import Any

from package.agent.llm.realtime import bind_text_delta_handler
from package.agent.observer.contracts import ExecutionEventSink
from package.agent.observer.events import ExecutionEvent, ExecutionEventType
from package.agent.runtime.contracts import AgentProgram
from package.agent.runtime.loop import RuntimePolicy
from package.agent.runtime.streaming import RuntimeStreamingEventSink


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    answer: str
    result: dict[str, Any] | None = None


class AgentRuntime:
    def __init__(
        self,
        *,
        program: AgentProgram,
        observer: ExecutionEventSink,
        policy: RuntimePolicy,
    ) -> None:
        self._program = program
        self._observer = observer
        self._policy = policy

    async def run(
        self,
        *,
        execution_id: str,
        session_id: str,
        question: str,
    ) -> RuntimeResult:
        await self._observer.emit(
            ExecutionEvent(
                execution_id=execution_id,
                type=ExecutionEventType.EXECUTION_STARTED,
                payload={"session_id": session_id},
            )
        )

        streaming_observer = RuntimeStreamingEventSink(
            delegate=self._observer,
            execution_id=execution_id,
        )

        try:
            with bind_text_delta_handler(streaming_observer.emit_model_delta):
                program_result = await self._program.execute(
                    execution_id=execution_id,
                    session_id=session_id,
                    question=question,
                    observer=streaming_observer,
                    policy=self._policy,
                )
            result = RuntimeResult(
                answer=program_result.answer,
                result=program_result.result,
            )
            await self._observer.emit(
                ExecutionEvent(
                    execution_id=execution_id,
                    type=ExecutionEventType.EXECUTION_COMPLETED,
                    payload={"answer": result.answer, "result": result.result},
                )
            )
            return result
        except Exception as exc:
            await self._observer.emit(
                ExecutionEvent(
                    execution_id=execution_id,
                    type=ExecutionEventType.EXECUTION_FAILED,
                    payload={"error": str(exc)},
                )
            )
            raise
