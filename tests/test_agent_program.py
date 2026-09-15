from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest

from package.agent.llm.models import (
    LLMChunk,
    LLMMessage,
    LLMResponse,
    LLMToolCall,
    LLMToolDefinition,
    MessageRole,
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


@pytest.mark.asyncio
async def test_agent_can_answer_without_calling_tools() -> None:
    llm = FakeLLM([LLMResponse(content="Resposta direta.")])
    observer = RecordingObserver()
    program = LangGraphAgentProgram(llm=llm, tools=ToolRegistry())

    result = await program.execute(
        execution_id="execution-1",
        session_id="session-1",
        question="Responda diretamente",
        observer=observer,
        policy=RuntimePolicy(max_iterations=3, max_sql_retries=2),
    )

    assert result.answer == "Resposta direta."
    assert result.result == {"iterations": 1, "tool_calls": 0, "stop_reason": "answer"}
    assert len(llm.calls) == 1
    assert [message.role for message in llm.calls[0]] == [MessageRole.SYSTEM, MessageRole.USER]
    assert llm.tools == [()]
    assert [event.type for event in observer.events] == [
        ExecutionEventType.AGENT_ITERATION_STARTED,
        ExecutionEventType.LLM_STARTED,
        ExecutionEventType.LLM_COMPLETED,
        ExecutionEventType.AGENT_DECISION,
        ExecutionEventType.ANSWER_GENERATED,
        ExecutionEventType.ASSISTANT_DELTA,
    ]


@pytest.mark.asyncio
async def test_agent_executes_all_tool_calls_before_next_reasoning_step() -> None:
    llm = FakeLLM(
        [
            LLMResponse(
                tool_calls=(
                    LLMToolCall(id="call-1", name="lookup", arguments={"value": "SC"}),
                    LLMToolCall(id="call-2", name="lookup", arguments={"value": "SP"}),
                )
            ),
            LLMResponse(content="Duas consultas concluídas."),
        ]
    )
    tool = FakeTool()
    program = LangGraphAgentProgram(
        llm=llm,
        tools=ToolRegistry([tool]),
    )

    result = await program.execute(
        execution_id="execution-1",
        session_id="session-1",
        question="Consulte dois valores",
        observer=RecordingObserver(),
        policy=RuntimePolicy(max_iterations=3, max_sql_retries=2),
    )

    assert result.answer == "Duas consultas concluídas."
    assert result.result["tool_calls"] == 2
    assert tool.calls == [{"value": "SC"}, {"value": "SP"}]

    tool_messages = [message for message in llm.calls[1] if message.role == MessageRole.TOOL]
    assert [message.tool_call_id for message in tool_messages] == ["call-1", "call-2"]
    assert all('\"ok\": true' in message.content for message in tool_messages)

    definitions = llm.tools[0]
    assert len(definitions) == 1
    assert definitions[0].name == "lookup"
    assert definitions[0].input_schema == FakeTool.input_schema


@pytest.mark.asyncio
async def test_unknown_tool_is_returned_to_agent_as_recoverable_error() -> None:
    llm = FakeLLM(
        [
            LLMResponse(
                tool_calls=(
                    LLMToolCall(id="call-unknown", name="missing", arguments={}),
                )
            ),
            LLMResponse(content="Recuperei da ferramenta inexistente."),
        ]
    )
    observer = RecordingObserver()
    program = LangGraphAgentProgram(llm=llm, tools=ToolRegistry())

    result = await program.execute(
        execution_id="execution-1",
        session_id="session-1",
        question="Tente uma ferramenta inexistente",
        observer=observer,
        policy=RuntimePolicy(max_iterations=3, max_sql_retries=2),
    )

    assert result.answer == "Recuperei da ferramenta inexistente."
    assert len(llm.calls) == 2
    tool_messages = [message for message in llm.calls[1] if message.role == MessageRole.TOOL]
    assert len(tool_messages) == 1
    assert tool_messages[0].tool_call_id == "call-unknown"
    assert '\"ok\": false' in tool_messages[0].content
    assert "Unknown tool: missing" in tool_messages[0].content
    assert ExecutionEventType.TOOL_FAILED in [event.type for event in observer.events]
