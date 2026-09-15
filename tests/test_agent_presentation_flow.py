from collections.abc import AsyncIterator, Sequence
from types import SimpleNamespace

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
from package.agent.tools.presentation.tool import PresentationTool
from package.agent.tools.registry import ToolRegistry


class RecordingObserver:
    def __init__(self) -> None:
        self.events: list[ExecutionEvent] = []

    async def emit(self, event: ExecutionEvent) -> None:
        self.events.append(event)


class FakeLLM:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = iter(responses)

    async def invoke(
        self,
        messages: Sequence[LLMMessage],
        *,
        tools: Sequence[LLMToolDefinition] = (),
    ) -> LLMResponse:
        return next(self._responses)

    async def stream(self, messages: Sequence[LLMMessage]) -> AsyncIterator[LLMChunk]:
        if False:
            yield LLMChunk(content="")


class FakeContextManager:
    def tool_definitions(self, tools: ToolRegistry) -> tuple[LLMToolDefinition, ...]:
        return tuple(
            LLMToolDefinition(
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
            )
            for tool in tools.all()
        )

    async def load_context(self, *, session_id, execution_id, question, tools):
        return SimpleNamespace(
            history=(),
            snapshot=None,
            skills=(),
            tools=tuple(SimpleNamespace(name=tool.name) for tool in tools.all()),
            question=question,
        )

    def initial_messages(self, context) -> list[LLMMessage]:
        return [
            LLMMessage(role=MessageRole.SYSTEM, content="Use evidence only."),
            LLMMessage(role=MessageRole.USER, content=context.question),
        ]

    async def prepare_reasoning(
        self,
        messages,
        *,
        session_id,
        execution_id,
        question,
        tool_definitions,
        skill_names=(),
    ):
        return SimpleNamespace(
            persistent_messages=list(messages),
            reasoning_messages=list(messages),
            budget=SimpleNamespace(dynamic_tokens=10, dynamic_budget_tokens=10_000),
            snapshot=None,
        )

    def is_skill_request(self, call: LLMToolCall) -> bool:
        return False

    def is_global_context_search(self, call: LLMToolCall) -> bool:
        return False

    async def record_tool_observation(self, **kwargs) -> None:
        return None

    async def finalize_execution(self, **kwargs):
        return SimpleNamespace(
            sequence=1,
            reason=SimpleNamespace(value="execution_completed"),
            estimated_tokens=10,
        )


@pytest.mark.asyncio
async def test_agent_persists_presentation_artifact_in_result() -> None:
    presentation_arguments = {
        "data": {
            "columns": ["canal", "reclamacoes"],
            "rows": [
                {"canal": "Telefone", "reclamacoes": 19},
                {"canal": "Chat", "reclamacoes": 18},
                {"canal": "E-mail", "reclamacoes": 14},
            ],
        },
        "visualization": {
            "type": "bar",
            "title": "Reclamações não resolvidas por canal",
            "x": "canal",
            "y": ["reclamacoes"],
        },
    }
    llm = FakeLLM(
        [
            LLMResponse(
                tool_calls=(
                    LLMToolCall(
                        id="present-1",
                        name="present_result",
                        arguments=presentation_arguments,
                    ),
                )
            ),
            LLMResponse(content="Telefone possui o maior número de reclamações não resolvidas."),
        ]
    )
    observer = RecordingObserver()
    program = LangGraphAgentProgram(
        llm=llm,
        tools=ToolRegistry([PresentationTool()]),
        context_manager=FakeContextManager(),
    )

    result = await program.execute(
        execution_id="execution-visualization",
        session_id="session-visualization",
        question="Mostre as reclamações não resolvidas por canal.",
        observer=observer,
        policy=RuntimePolicy(
            max_iterations=4,
            max_sql_retries=2,
            max_parallel_tool_calls_per_tool=2,
        ),
    )

    assert result.answer == "Telefone possui o maior número de reclamações não resolvidas."
    assert result.result["presentation"]["visualization"]["type"] == "bar"
    assert result.result["presentation"]["visualization"]["x"] == "canal"
    assert result.result["presentation"]["data"]["rows"][0] == {
        "canal": "Telefone",
        "reclamacoes": 19,
    }
    assert any(
        event.type == ExecutionEventType.VISUALIZATION_SELECTED
        and event.payload["type"] == "bar"
        for event in observer.events
    )
