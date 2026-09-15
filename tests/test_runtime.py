from dataclasses import dataclass

import pytest

from package.agent.observer.events import ExecutionEvent, ExecutionEventType
from package.agent.runtime.execution import AgentRuntime


class RecordingObserver:
    def __init__(self) -> None:
        self.events: list[ExecutionEvent] = []

    async def emit(self, event: ExecutionEvent) -> None:
        self.events.append(event)


@dataclass
class ProgramResult:
    answer: str
    result: dict | None = None


class Program:
    async def execute(self, *, execution_id, session_id, question, observer):
        await observer.emit(
            ExecutionEvent(
                execution_id=execution_id,
                type=ExecutionEventType.PLAN_CREATED,
                payload={"question": question},
            )
        )
        return ProgramResult(answer="ok", result={"rows": 1})


@pytest.mark.asyncio
async def test_runtime_emits_lifecycle_events() -> None:
    observer = RecordingObserver()
    runtime = AgentRuntime(program=Program(), observer=observer)

    result = await runtime.run(
        execution_id="execution-1",
        session_id="session-1",
        question="question",
    )

    assert result.answer == "ok"
    assert [event.type for event in observer.events] == [
        ExecutionEventType.EXECUTION_STARTED,
        ExecutionEventType.PLAN_CREATED,
        ExecutionEventType.EXECUTION_COMPLETED,
    ]
