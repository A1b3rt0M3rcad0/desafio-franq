from datetime import datetime, timezone

import pytest

from package.agent.cache.event_stream import StreamEvent
from package.agent.observer.events import ExecutionEvent, ExecutionEventType
from package.agent.observer.observer import (
    ExecutionObservationGapError,
    RedisExecutionObserver,
)
from package.agent.observer.projection import (
    initial_projection,
    public_event,
    reduce_projection,
)
from package.agent.observer.publisher import RedisExecutionEventSink


class FakeHotState:
    def __init__(self) -> None:
        self.states: dict[str, dict] = {}
        self.expired: list[str] = []

    async def get(self, execution_id: str):
        state = self.states.get(execution_id)
        return dict(state) if state is not None else None

    async def set(self, execution_id: str, state: dict) -> None:
        self.states[execution_id] = dict(state)

    async def expire(self, execution_id: str) -> None:
        self.expired.append(execution_id)


class FakeEventStream:
    def __init__(self) -> None:
        self.events: list[StreamEvent] = []
        self.live_batches: list[list[StreamEvent]] = []
        self.expired: list[str] = []

    async def append(self, *, execution_id: str, event_type: str, payload: dict):
        sequence = len(self.events) + 1
        event = StreamEvent(
            stream_id=f"{sequence}-0",
            sequence=sequence,
            event_type=event_type,
            payload=dict(payload),
        )
        self.events.append(event)
        return event

    async def retained(self, execution_id: str) -> list[StreamEvent]:
        return list(self.events)

    async def latest(self, execution_id: str) -> StreamEvent | None:
        return self.events[-1] if self.events else None

    async def read(self, execution_id: str, *, after: str = "0-0") -> list[StreamEvent]:
        if not self.live_batches:
            return []
        return self.live_batches.pop(0)

    async def expire(self, execution_id: str) -> None:
        self.expired.append(execution_id)


class FakeDurableState:
    def __init__(self, state: dict | None) -> None:
        self.state = state

    async def get(self, execution_id: str):
        if self.state is None:
            return None
        return {"execution_id": execution_id, **self.state}


def _payload(**values):
    return {"created_at": datetime.now(timezone.utc).isoformat(), **values}


def _observer(hot, stream, durable) -> RedisExecutionObserver:
    return RedisExecutionObserver(
        hot_state=hot,
        event_stream=stream,
        durable_state=durable,
        acceptance_poll_seconds=0.001,
        projection_max_activities=20,
    )


def test_public_event_exposes_only_whitelisted_observation_fields() -> None:
    event = ExecutionEvent(
        execution_id="execution-1",
        type=ExecutionEventType.TOOL_STARTED,
        payload={
            "iteration": 2,
            "tool": "database",
            "tool_call_id": "call-1",
            "arguments": {"sql": "SELECT 1"},
            "private_internal_value": "must-not-leak",
        },
    )

    event_type, payload = public_event(event)

    assert event_type == "tool.started"
    assert payload["arguments"] == {"sql": "SELECT 1"}
    assert "private_internal_value" not in payload


@pytest.mark.asyncio
async def test_event_sink_rebuilds_partial_answer_from_hot_projection_after_restart() -> None:
    hot = FakeHotState()
    stream = FakeEventStream()
    first_sink = RedisExecutionEventSink(
        hot_state=hot,
        event_stream=stream,
        projection_max_activities=20,
    )

    await first_sink.emit(
        ExecutionEvent(
            execution_id="execution-1",
            type=ExecutionEventType.EXECUTION_STARTED,
            payload={"session_id": "session-1"},
        )
    )
    await first_sink.emit(
        ExecutionEvent(
            execution_id="execution-1",
            type=ExecutionEventType.ASSISTANT_DELTA,
            payload={"content": "Olá"},
        )
    )

    restarted_sink = RedisExecutionEventSink(
        hot_state=hot,
        event_stream=stream,
        projection_max_activities=20,
    )
    await restarted_sink.emit(
        ExecutionEvent(
            execution_id="execution-1",
            type=ExecutionEventType.ASSISTANT_DELTA,
            payload={"content": " mundo"},
        )
    )

    assert hot.states["execution-1"]["partial_answer"] == "Olá mundo"
    assert hot.states["execution-1"]["sequence"] == 3


@pytest.mark.asyncio
async def test_current_state_falls_back_to_durable_pending_before_hot_state_exists() -> None:
    hot = FakeHotState()
    stream = FakeEventStream()
    durable = FakeDurableState(
        {
            "session_id": "session-1",
            "status": "pending",
            "answer": None,
            "error": None,
            "result": None,
        }
    )

    frame = await _observer(hot, stream, durable).current_state("execution-1")

    assert frame.type == "execution.state"
    assert frame.sequence is None
    assert frame.payload["status"] == "pending"
    assert frame.payload["realtime_available"] is False


@pytest.mark.asyncio
async def test_reattach_returns_projection_at_high_watermark_then_live_tail() -> None:
    hot = FakeHotState()
    stream = FakeEventStream()
    durable = FakeDurableState(
        {
            "session_id": "session-1",
            "status": "running",
            "answer": None,
            "error": None,
            "result": None,
        }
    )

    projection = initial_projection("execution-1", await durable.get("execution-1"))
    first = StreamEvent(
        stream_id="1-0",
        sequence=1,
        event_type="execution.started",
        payload=_payload(session_id="session-1"),
    )
    projection = reduce_projection(
        projection,
        event_type=first.event_type,
        payload=first.payload,
        sequence=1,
        max_activities=20,
    )
    hot.states["execution-1"] = projection

    stream.events = [
        first,
        StreamEvent(
            stream_id="2-0",
            sequence=2,
            event_type="tool.started",
            payload=_payload(
                iteration=1,
                tool="database",
                tool_call_id="call-1",
                arguments={"sql": "SELECT 1"},
            ),
        ),
        StreamEvent(
            stream_id="3-0",
            sequence=3,
            event_type="tool.completed",
            payload=_payload(
                iteration=1,
                tool="database",
                tool_call_id="call-1",
                result={"row_count": 1},
            ),
        ),
    ]
    stream.live_batches = [
        [
            StreamEvent(
                stream_id="4-0",
                sequence=4,
                event_type="assistant.delta",
                payload=_payload(content="Resposta"),
            ),
            StreamEvent(
                stream_id="5-0",
                sequence=5,
                event_type="execution.completed",
                payload=_payload(answer="Resposta", result={"iterations": 1}),
            ),
        ]
    ]

    frames = []
    async for frame in _observer(hot, stream, durable).observe(
        "execution-1",
        last_sequence=1,
    ):
        frames.append(frame)

    assert [frame.type for frame in frames] == [
        "execution.state",
        "assistant.delta",
        "execution.completed",
    ]
    assert frames[0].sequence == 3
    assert frames[0].payload["reattached_from_sequence"] == 1
    assert frames[0].payload["realtime_available"] is True
    assert frames[0].payload["active_tools"] == []
    assert frames[1].sequence == 4
    assert frames[2].sequence == 5


@pytest.mark.asyncio
async def test_projection_gap_is_detected_instead_of_inventing_continuity() -> None:
    hot = FakeHotState()
    stream = FakeEventStream()
    durable = FakeDurableState(
        {
            "session_id": "session-1",
            "status": "running",
            "answer": None,
            "error": None,
            "result": None,
        }
    )
    projection = initial_projection("execution-1", await durable.get("execution-1"))
    projection["sequence"] = 1
    hot.states["execution-1"] = projection
    stream.events = [
        StreamEvent(
            stream_id="3-0",
            sequence=3,
            event_type="tool.started",
            payload=_payload(
                iteration=2,
                tool="database",
                tool_call_id="call-2",
                arguments={},
            ),
        )
    ]

    with pytest.raises(ExecutionObservationGapError):
        await _observer(hot, stream, durable).current_state("execution-1")
