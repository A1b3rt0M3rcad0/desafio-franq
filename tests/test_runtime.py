from dataclasses import dataclass

import pytest

from package.agent.observer.events import ExecutionEvent, ExecutionEventType
from package.agent.runtime.execution import AgentRuntime
from package.agent.runtime.loop import RuntimePolicy


class RecordingEventSink:
    def __init__(self) -> None:
        self.events: list[ExecutionEvent] = []

    async def emit(self, event: ExecutionEvent) -> None:
        self.events.append(event)


@dataclass
class ProgramResult:
    answer: str
    result: dict | None = None


class Program:
    async def execute(self, *, execution_id, session_id, question, observer, policy):
        assert policy.max_iterations == 8
        assert policy.max_sql_retries == 3
        assert policy.max_parallel_tool_calls_per_tool == 3
        await observer.emit(
            ExecutionEvent(
                execution_id=execution_id,
                type=ExecutionEventType.PLAN_CREATED,
                payload={"question": question},
            )
        )
        return ProgramResult(answer="ok", result={"rows": 1})


@pytest.mark.asyncio
async def test_runtime_only_emits_program_events() -> None:
    event_sink = RecordingEventSink()
    runtime = AgentRuntime(
        program=Program(),
        event_sink=event_sink,
        policy=RuntimePolicy(
            max_iterations=8,
            max_sql_retries=3,
            max_parallel_tool_calls_per_tool=3,
        ),
    )

    result = await runtime.run(
        execution_id="execution-1",
        session_id="session-1",
        question="question",
    )

    assert result.answer == "ok"
    assert [event.type for event in event_sink.events] == [ExecutionEventType.PLAN_CREATED]
