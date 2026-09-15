import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest

from package.agent.context.budget import (
    ApproximateTokenEstimator,
    ContextBudgetManager,
    ContextBudgetPolicy,
)
from package.agent.context.builder import ContextBuilder
from package.agent.context.manager import ContextManager, SKILL_REQUEST_TOOL_NAME
from package.agent.context.memory import (
    InMemoryContextSnapshotStore,
    InMemoryGlobalContextStore,
)
from package.agent.context.models import ContextSummary, GlobalContextKind
from package.agent.context.retrieval import (
    GLOBAL_CONTEXT_SEARCH_TOOL_NAME,
    GlobalContextRetriever,
)
from package.agent.llm.models import (
    LLMChunk,
    LLMMessage,
    LLMResponse,
    LLMToolCall,
    LLMToolDefinition,
    MessageRole,
)
from package.agent.observer.events import ExecutionEvent, ExecutionEventType
from package.agent.prompt.system import SYSTEM_PROMPT
from package.agent.runtime.loop import RuntimePolicy
from package.agent.runtime.program import LangGraphAgentProgram
from package.agent.skills.registry import SkillRegistry
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


class FakeSummarizer:
    async def summarize(self, *, previous_snapshot, messages, question):
        facts = [
            message.content
            for message in messages
            if message.role == MessageRole.ASSISTANT and message.content.strip()
        ]
        return ContextSummary(
            current_request=question,
            established_facts=facts[-3:],
            continuity_notes=["execution compacted"],
        )


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


class FakeSkill:
    name = "sql_reasoning"
    description = "Guidance for reasoning about analytical SQL."

    def __init__(self) -> None:
        self.load_count = 0

    async def load(self) -> str:
        self.load_count += 1
        return "FULL SKILL CONTENT: validate joins and aggregates before querying."


class ConcurrentTool:
    name = "concurrent_lookup"
    description = "Lookup values concurrently"
    input_schema = {
        "type": "object",
        "properties": {"value": {"type": "integer"}},
        "required": ["value"],
    }

    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.calls: list[int] = []

    async def invoke(self, arguments: dict[str, Any]) -> Any:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            value = int(arguments["value"])
            self.calls.append(value)
            await asyncio.sleep(0.02)
            return {"value": value}
        finally:
            self.active -= 1


def _policy(*, max_iterations: int = 4, max_parallel: int = 3) -> RuntimePolicy:
    return RuntimePolicy(
        max_iterations=max_iterations,
        max_sql_retries=2,
        max_parallel_tool_calls_per_tool=max_parallel,
    )


def _program_components(
    llm: FakeLLM,
    *,
    tools: list[Any] | None = None,
    skills: list[Any] | None = None,
):
    tool_registry = ToolRegistry(tools or [])
    snapshots = InMemoryContextSnapshotStore()
    global_context = InMemoryGlobalContextStore()
    context_manager = ContextManager(
        builder=ContextBuilder(),
        skills=SkillRegistry(skills or []),
        system_prompt=SYSTEM_PROMPT,
        budget_manager=ContextBudgetManager(
            estimator=ApproximateTokenEstimator(chars_per_token=4.0),
            policy=ContextBudgetPolicy(
                model_context_window_tokens=1_000_000,
                dynamic_context_percentage=25.0,
            ),
        ),
        summarizer=FakeSummarizer(),
        snapshot_store=snapshots,
        global_context_store=global_context,
        retriever=GlobalContextRetriever(
            store=global_context,
            default_limit=5,
            max_limit=10,
        ),
    )
    program = LangGraphAgentProgram(
        llm=llm,
        tools=tool_registry,
        context_manager=context_manager,
    )
    return program, snapshots, global_context


def _program(
    llm: FakeLLM,
    *,
    tools: list[Any] | None = None,
    skills: list[Any] | None = None,
) -> LangGraphAgentProgram:
    program, _, _ = _program_components(llm, tools=tools, skills=skills)
    return program


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
    program = _program(llm, tools=[tool])

    result = await program.execute(
        execution_id="execution-1",
        session_id="session-1",
        question="Qual é o resultado?",
        observer=observer,
        policy=_policy(),
    )

    assert result.answer == "Resultado encontrado."
    assert result.result == {
        "iterations": 2,
        "tool_calls": 1,
        "skill_uses": 0,
        "stop_reason": "answer",
    }
    assert tool.calls == [{"value": "SC"}]
    assert len(llm.calls) == 2
    assert any(message.tool_call_id == "call-1" for message in llm.calls[1])
    event_types = [event.type for event in observer.events]
    assert ExecutionEventType.CONTEXT_LOADED in event_types
    assert ExecutionEventType.TOOL_COMPLETED in event_types
    assert ExecutionEventType.ANSWER_GENERATED in event_types
    assert ExecutionEventType.CONTEXT_SNAPSHOT_CREATED in event_types


@pytest.mark.asyncio
async def test_skill_content_is_loaded_for_one_reasoning_step_only() -> None:
    skill = FakeSkill()
    tool = FakeTool()
    llm = FakeLLM(
        [
            LLMResponse(
                tool_calls=(
                    LLMToolCall(
                        id="skill-1",
                        name=SKILL_REQUEST_TOOL_NAME,
                        arguments={"skills": [skill.name]},
                    ),
                )
            ),
            LLMResponse(
                tool_calls=(
                    LLMToolCall(id="call-1", name="lookup", arguments={"value": "SC"}),
                )
            ),
            LLMResponse(content="Concluído com a skill."),
        ]
    )
    observer = RecordingObserver()
    program = _program(llm, tools=[tool], skills=[skill])

    result = await program.execute(
        execution_id="execution-1",
        session_id="session-1",
        question="Analise os dados",
        observer=observer,
        policy=_policy(max_iterations=5),
    )

    assert result.answer == "Concluído com a skill."
    assert result.result["skill_uses"] == 1
    assert skill.load_count == 1

    first_prompt = "\n".join(message.content for message in llm.calls[0])
    assert skill.name in first_prompt
    assert skill.description in first_prompt
    assert "FULL SKILL CONTENT" not in first_prompt

    second_call = llm.calls[1]
    active_skill_messages = [
        message for message in second_call if message.role == MessageRole.DEVELOPER
    ]
    assert len(active_skill_messages) == 1
    assert "FULL SKILL CONTENT" in active_skill_messages[0].content

    third_call = llm.calls[2]
    assert all("FULL SKILL CONTENT" not in message.content for message in third_call)
    assert any(message.tool_call_id == "skill-1" for message in third_call)

    event_types = [event.type for event in observer.events]
    assert ExecutionEventType.SKILL_REQUESTED in event_types
    assert ExecutionEventType.SKILL_CONTEXT_LOADED in event_types
    assert ExecutionEventType.SKILL_CONTEXT_RELEASED in event_types


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
    program = _program(llm, tools=[FakeTool(fail=True)])

    result = await program.execute(
        execution_id="execution-1",
        session_id="session-1",
        question="Teste",
        observer=observer,
        policy=_policy(),
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
    program = _program(llm, tools=[FakeTool()])

    result = await program.execute(
        execution_id="execution-1",
        session_id="session-1",
        question="Nunca conclua",
        observer=observer,
        policy=_policy(max_iterations=2),
    )

    assert result.result["iterations"] == 2
    assert result.result["stop_reason"] == "max_iterations"
    assert len(llm.calls) == 2
    assert ExecutionEventType.AGENT_MAX_ITERATIONS_REACHED in [
        event.type for event in observer.events
    ]


@pytest.mark.asyncio
async def test_agent_can_answer_without_calling_external_tools() -> None:
    llm = FakeLLM([LLMResponse(content="Resposta direta.")])
    observer = RecordingObserver()
    program = _program(llm)

    result = await program.execute(
        execution_id="execution-1",
        session_id="session-1",
        question="Responda diretamente",
        observer=observer,
        policy=_policy(),
    )

    assert result.answer == "Resposta direta."
    assert result.result == {
        "iterations": 1,
        "tool_calls": 0,
        "skill_uses": 0,
        "stop_reason": "answer",
    }
    assert len(llm.calls) == 1
    assert [message.role for message in llm.calls[0]] == [MessageRole.SYSTEM, MessageRole.USER]
    assert [definition.name for definition in llm.tools[0]] == [
        GLOBAL_CONTEXT_SEARCH_TOOL_NAME
    ]

    event_types = [event.type for event in observer.events]
    required_events = [
        ExecutionEventType.CONTEXT_LOADED,
        ExecutionEventType.AGENT_ITERATION_STARTED,
        ExecutionEventType.LLM_STARTED,
        ExecutionEventType.LLM_COMPLETED,
        ExecutionEventType.AGENT_DECISION,
        ExecutionEventType.ANSWER_STARTED,
        ExecutionEventType.ASSISTANT_DELTA,
        ExecutionEventType.ANSWER_GENERATED,
        ExecutionEventType.ANSWER_COMPLETED,
        ExecutionEventType.CONTEXT_SNAPSHOT_CREATED,
    ]
    for event_type in required_events:
        assert event_type in event_types

    positions = [event_types.index(event_type) for event_type in required_events]
    assert positions == sorted(positions)


@pytest.mark.asyncio
async def test_same_tool_is_limited_to_three_parallel_operations() -> None:
    tool = ConcurrentTool()
    calls = tuple(
        LLMToolCall(
            id=f"call-{index}",
            name=tool.name,
            arguments={"value": index},
        )
        for index in range(5)
    )
    llm = FakeLLM(
        [
            LLMResponse(tool_calls=calls),
            LLMResponse(content="Todas as consultas terminaram."),
        ]
    )
    program = _program(llm, tools=[tool])

    result = await program.execute(
        execution_id="execution-1",
        session_id="session-1",
        question="Execute cinco consultas",
        observer=RecordingObserver(),
        policy=_policy(max_parallel=3),
    )

    assert result.result["tool_calls"] == 5
    assert sorted(tool.calls) == [0, 1, 2, 3, 4]
    assert tool.max_active == 3


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
    program = _program(llm)

    result = await program.execute(
        execution_id="execution-1",
        session_id="session-1",
        question="Tente uma ferramenta inexistente",
        observer=observer,
        policy=_policy(),
    )

    assert result.answer == "Recuperei da ferramenta inexistente."
    tool_messages = [message for message in llm.calls[1] if message.role == MessageRole.TOOL]
    assert len(tool_messages) == 1
    assert tool_messages[0].tool_call_id == "call-unknown"
    assert '\"ok\": false' in tool_messages[0].content
    assert "Unknown tool: missing" in tool_messages[0].content
    assert ExecutionEventType.TOOL_FAILED in [event.type for event in observer.events]


@pytest.mark.asyncio
async def test_agent_can_retrieve_information_lost_from_current_snapshot() -> None:
    llm = FakeLLM(
        [
            LLMResponse(
                tool_calls=(
                    LLMToolCall(
                        id="context-1",
                        name=GLOBAL_CONTEXT_SEARCH_TOOL_NAME,
                        arguments={"query": "WhatsApp maio"},
                    ),
                )
            ),
            LLMResponse(content="Recuperei a regra antiga."),
        ]
    )
    program, _, global_context = _program_components(llm)
    await global_context.append(
        session_id="session-1",
        execution_id="execution-old",
        kind=GlobalContextKind.USER_MESSAGE,
        content="Em maio, a campanha WhatsApp deve excluir clientes inativos.",
    )
    observer = RecordingObserver()

    result = await program.execute(
        execution_id="execution-1",
        session_id="session-1",
        question="Qual era a regra antiga?",
        observer=observer,
        policy=_policy(),
    )

    assert result.answer == "Recuperei a regra antiga."
    retrieved_messages = [
        message
        for message in llm.calls[1]
        if message.role == MessageRole.TOOL and message.tool_call_id == "context-1"
    ]
    assert len(retrieved_messages) == 1
    assert "excluir clientes inativos" in retrieved_messages[0].content
    assert ExecutionEventType.CONTEXT_RETRIEVED in [event.type for event in observer.events]


@pytest.mark.asyncio
async def test_next_execution_starts_from_previous_execution_snapshot() -> None:
    llm = FakeLLM(
        [
            LLMResponse(content="Conclusão da primeira execução."),
            LLMResponse(content="Continuidade da segunda execução."),
        ]
    )
    program, snapshots, _ = _program_components(llm)

    await program.execute(
        execution_id="execution-1",
        session_id="session-1",
        question="Primeiro pedido",
        observer=RecordingObserver(),
        policy=_policy(),
    )
    await program.execute(
        execution_id="execution-2",
        session_id="session-1",
        question="Continue",
        observer=RecordingObserver(),
        policy=_policy(),
    )

    assert len(snapshots.snapshots) == 2
    second_prompt = "\n".join(message.content for message in llm.calls[1])
    assert "Conclusão da primeira execução." in second_prompt
    assert "Session continuity snapshot" in second_prompt
