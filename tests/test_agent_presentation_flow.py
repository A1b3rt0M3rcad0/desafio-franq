from collections.abc import AsyncIterator, Sequence
from types import SimpleNamespace

import pytest

from package.agent.llm.models import (
    LLMChunk,
    LLMMessage,
    LLMResponse,
    LLMToolDefinition,
    MessageRole,
)
from package.agent.runtime.loop import RuntimePolicy
from package.agent.runtime.program import LangGraphAgentProgram
from package.agent.tools.registry import ToolRegistry


RICH_ANSWER = """Os canais apresentam volumes diferentes de reclamações.

```visualization
{"version":1,"type":"bar","title":"Reclamações por canal","data":{"columns":["canal","reclamacoes"],"rows":[{"canal":"Telefone","reclamacoes":19},{"canal":"Chat","reclamacoes":18}]},"x":"canal","y":["reclamacoes"]}
```

Ao longo do período também houve variação mensal.

```visualization
{"version":1,"type":"line","title":"Reclamações por mês","data":{"columns":["mes","reclamacoes"],"rows":[{"mes":"2025-01","reclamacoes":10},{"mes":"2025-02","reclamacoes":14}]},"x":"mes","y":["reclamacoes"]}
```

Telefone lidera o recorte por canal."""


class RecordingObserver:
    async def emit(self, event) -> None:
        return None


class FakeLLM:
    async def invoke(
        self,
        messages: Sequence[LLMMessage],
        *,
        tools: Sequence[LLMToolDefinition] = (),
    ) -> LLMResponse:
        return LLMResponse(content="Rascunho baseado nas evidências.")

    async def stream(self, messages: Sequence[LLMMessage]) -> AsyncIterator[LLMChunk]:
        midpoint = len(RICH_ANSWER) // 2
        yield LLMChunk(content=RICH_ANSWER[:midpoint])
        yield LLMChunk(content=RICH_ANSWER[midpoint:])


class FakeContextManager:
    def __init__(self) -> None:
        self.finalized_answer: str | None = None

    def tool_definitions(self, tools: ToolRegistry) -> tuple[LLMToolDefinition, ...]:
        return ()

    async def load_context(self, *, session_id, execution_id, question, tools):
        return SimpleNamespace(
            history=(),
            snapshot=None,
            skills=(),
            tools=(),
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

    def is_skill_request(self, call) -> bool:
        return False

    def is_global_context_search(self, call) -> bool:
        return False

    async def record_tool_observation(self, **kwargs) -> None:
        return None

    async def finalize_execution(self, **kwargs):
        self.finalized_answer = kwargs["answer"]
        return SimpleNamespace(
            sequence=1,
            reason=SimpleNamespace(value="execution_completed"),
            estimated_tokens=10,
        )


@pytest.mark.asyncio
async def test_agent_can_stream_multiple_inline_visualizations_in_one_answer() -> None:
    context_manager = FakeContextManager()
    program = LangGraphAgentProgram(
        llm=FakeLLM(),
        tools=ToolRegistry([]),
        context_manager=context_manager,
    )

    result = await program.execute(
        execution_id="execution-visualization",
        session_id="session-visualization",
        question="Analise reclamações por canal e ao longo do tempo.",
        observer=RecordingObserver(),
        policy=RuntimePolicy(
            max_iterations=4,
            max_sql_retries=2,
            max_parallel_tool_calls_per_tool=2,
        ),
    )

    assert result.answer == RICH_ANSWER
    assert result.answer.count("```visualization") == 2
    assert "presentation" not in result.result
    assert result.result == {
        "iterations": 1,
        "tool_calls": 0,
        "skill_uses": 0,
        "stop_reason": "answer",
    }
    assert context_manager.finalized_answer == RICH_ANSWER
