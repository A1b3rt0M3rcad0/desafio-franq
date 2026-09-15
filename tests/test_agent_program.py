from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest

from package.agent.llm.models import (
    LLMChunk,
    LLMMessage,
    LLMResponse,
    LLMToolCall,
    LLMToolDefinition,
)
from package.agent.observer.events import ExecutionEvent, ExecutionEventType
from package.agent.runtime.loop import RuntimePolicy
from package.agent.runtime.program import LangGraphAgentProgram
from package.agent.tools.registry import ToolRegistry


class RecordingObserver:
    def __init__(self) -> None:
        self.events: list[ExecutionEvent] = []

    async def emit(self, event: ExecutionEvent) -> None:
        self.events.append(event)


class FakeLLM:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = iter(responses)
        self.calls: list[list[LLMMessage]] = []
        self.tools: list[tuple[LLMToolDefinition, ...]] = []

    async def invoke(
        self,
        messages: Sequence[LLMMessage],
        *,
        tools: Sequence[LLMToolDefinition] = (),
    ) -> LLMResponse:
        self.calls.append(list(messages))
        self.tools.append(tuple(tools))
        return next(self._responses)

    async def stream(self, messages: Sequence[LLMMessage]) -> AsyncIterator[LLMChunk]:
        if False:
            yield LLMChunk(content="")


class FakeTool:
    name = "lookup"
    description = "Lookup data"
    input_schema = {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
    }

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, Any]] = []

    async def invoke(self, arguments: dict[str, Any]) -> Any:
        self.calls.append(arguments)
        if self.fail:
            raise ValueError("tool failed")
        return {"value": arguments["value"]}


@pytest.mark.asyncio
async def test_agent_loops_from_tool_back_to_reasoning_until_answer() -> None:
    llm = FakeLLM(
        [
            LLMResponse(
                tool_calls=(
                    LLMToolCall(id="call-1", name="lookup", arguments={"value": "SC"}),
                )
            ),
            LLMResponse(content="Resultado encontrado."),
        ]
    )
    tool = FakeTool()
    observer = RecordingObserver()
    program = LangGraphAgentProgram(llm=llm, tools=ToolRegistry([tool]))

    result = await program.execute(
        execution_id="execution-1",
        session_id="session-1",
        question="Qual é o resultado?",
        observer=observer,
        policy=RuntimePolicy(max_iterations=4, max_sql_retries=2),
    )

    assert result.answer == "Resultado encontrado."
    assert result.result == {"iterations": 2, "tool_calls": 1, "stop_reason": "answer"}
    assert tool.calls == [{"value": "SC"}]
    assert len(llm.calls) == 2
    assert any(message.tool_call_id == "call-1" for message in llm.calls[1])
    assert ExecutionEventType.TOOL_COMPLETED in [event.type for event in observer.events]
    assert ExecutionEventType.ANSWER_GENERATED in [event.type for event in observer.events]


@pytest.mark.asyncio
async def test_tool_failure_returns_to_agent_instead_of_failing_execution() -> None:
    llm = FakeLLM(
        [
            LLMResponse(
                tool_calls=(
                    LLMToolCall(id="call-1", name="lookup", arguments={"value": "SC"}),
                )
            ),
            LLMResponse(content="Consegui responder após observar o erro."),
        ]
    )
    observer = RecordingObserver()
    program = LangGraphAgentProgram(
        llm=llm,
        tools=ToolRegistry([FakeTool(fail=True)]),
    )

    result = await program.execute(
        execution_id="execution-1",
        session_id="session-1",
        question="Teste",
        observer=observer,
        policy=RuntimePolicy(max_iterations=3, max_sql_retries=2),
    )

    assert result.answer == "Consegui responder após observar o erro."
    assert ExecutionEventType.TOOL_FAILED in [event.type for event in observer.events]
    tool_messages = [message for message in llm.calls[1] if message.tool_call_id == "call-1"]
    assert len(tool_messages) == 1
    assert '\"ok\": false' in tool_messages[0].content


@pytest.mark.asyncio
async def test_agent_stops_when_max_iterations_is_reached() -> None:
    llm = FakeLLM(
        [
            LLMResponse(
                tool_calls=(
                    LLMToolCall(id="call-1", name="lookup", arguments={"value": "1"}),
                )
            ),
            LLMResponse(
                tool_calls=(
                    LLMToolCall(id="call-2", name="lookup", arguments={"value": "2"}),
                )
            ),
        ]
    )
    observer = RecordingObserver()
    program = LangGraphAgentProgram(llm=llm, tools=ToolRegistry([FakeTool()]))

    result = await program.execute(
        execution_id="execution-1",
        session_id="session-1",
        question="Nunca conclua",
        observer=observer,
        policy=RuntimePolicy(max_iterations=2, max_sql_retries=2),
    )

    assert result.result["iterations"] == 2
    assert result.result["stop_reason"] == "max_iterations"
    assert len(llm.calls) == 2
    assert ExecutionEventType.AGENT_MAX_ITERATIONS_REACHED in [
        event.type for event in observer.events
    ]
