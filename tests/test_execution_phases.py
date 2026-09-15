from collections.abc import AsyncIterator

import pytest

from package.agent.llm.models import LLMChunk, LLMMessage, MessageRole
from package.agent.observer.events import ExecutionEvent, ExecutionEventType, ExecutionPhase
from package.agent.observer.projection import initial_projection, reduce_projection
from package.agent.runtime.program import LangGraphAgentProgram


class RecordingObserver:
    def __init__(self) -> None:
        self.events: list[ExecutionEvent] = []

    async def emit(self, event: ExecutionEvent) -> None:
        self.events.append(event)


class StreamingFinalLLM:
    async def stream(self, messages) -> AsyncIterator[LLMChunk]:
        assert messages[-1].role == MessageRole.DEVELOPER
        yield LLMChunk(content="Tudo ")
        yield LLMChunk(content="certo.")


@pytest.mark.asyncio
async def test_answer_node_streams_only_inside_authoritative_response_phase() -> None:
    program = object.__new__(LangGraphAgentProgram)
    program._llm = StreamingFinalLLM()
    observer = RecordingObserver()
    state = {
        "execution_id": "execution-1",
        "messages": [
            LLMMessage(role=MessageRole.USER, content="Olá"),
            LLMMessage(role=MessageRole.ASSISTANT, content="rascunho"),
        ],
        "answer": "rascunho",
        "stop_reason": "answer",
        "iteration": 1,
        "observer": observer,
    }

    result = await program._answer_node(state)

    assert result["answer"] == "Tudo certo."
    deltas = [
        event.payload["content"]
        for event in observer.events
        if event.type == ExecutionEventType.ASSISTANT_DELTA
    ]
    assert deltas == ["Tudo ", "certo."]

    phases = [
        event.payload["phase"]
        for event in observer.events
        if event.type == ExecutionEventType.EXECUTION_PHASE_CHANGED
    ]
    assert phases == [
        ExecutionPhase.RESPONSE_PREPARING.value,
        ExecutionPhase.RESPONSE_STREAMING.value,
        ExecutionPhase.FINALIZING.value,
    ]

    first_delta_index = next(
        index
        for index, event in enumerate(observer.events)
        if event.type == ExecutionEventType.ASSISTANT_DELTA
    )
    streaming_phase_index = next(
        index
        for index, event in enumerate(observer.events)
        if event.type == ExecutionEventType.EXECUTION_PHASE_CHANGED
        and event.payload["phase"] == ExecutionPhase.RESPONSE_STREAMING.value
    )
    assert streaming_phase_index < first_delta_index


def test_projection_never_regresses_from_streaming_back_to_preparing() -> None:
    state = initial_projection("execution-1")
    state = reduce_projection(
        state,
        event_type=ExecutionEventType.EXECUTION_PHASE_CHANGED.value,
        payload={"phase": ExecutionPhase.RESPONSE_STREAMING.value},
        sequence=1,
        max_activities=20,
    )
    state = reduce_projection(
        state,
        event_type=ExecutionEventType.EXECUTION_PHASE_CHANGED.value,
        payload={"phase": ExecutionPhase.RESPONSE_PREPARING.value},
        sequence=2,
        max_activities=20,
    )

    assert state["phase"] == ExecutionPhase.RESPONSE_STREAMING.value
    assert state["stage"] == ExecutionPhase.RESPONSE_STREAMING.value


def test_cancelled_projection_is_terminal() -> None:
    state = initial_projection("execution-1", {"status": "running"})
    state = reduce_projection(
        state,
        event_type=ExecutionEventType.EXECUTION_CANCELLED.value,
        payload={"reason": "user_requested"},
        sequence=1,
        max_activities=20,
    )
    state = reduce_projection(
        state,
        event_type=ExecutionEventType.EXECUTION_PHASE_CHANGED.value,
        payload={"phase": ExecutionPhase.REASONING.value},
        sequence=2,
        max_activities=20,
    )

    assert state["status"] == "cancelled"
    assert state["phase"] == ExecutionPhase.CANCELLED.value
