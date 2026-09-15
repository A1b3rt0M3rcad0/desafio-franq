from package.ui.client import ObservedFrame
from package.ui.observation import (
    FrameKind,
    apply_observed_frame,
    classify_frame,
    new_observation_state,
)


def _frame(
    event_type: str,
    *,
    sequence: int | None = 1,
    payload: dict | None = None,
) -> ObservedFrame:
    return ObservedFrame(
        execution_id="execution-1",
        type=event_type,
        sequence=sequence,
        payload=payload or {},
    )


def test_assistant_delta_starts_response_without_becoming_activity() -> None:
    active = new_observation_state("execution-1")

    update = apply_observed_frame(
        active,
        _frame("assistant.delta", payload={"content": "Olá"}),
    )

    assert update.kind == FrameKind.RESPONSE
    assert update.content_changed is True
    assert update.response_started is True
    assert active["content"] == "Olá"
    assert active["phase"] == "response_streaming"
    assert active["activities"] == []


def test_finalizing_after_response_never_resets_response_started_latch() -> None:
    active = new_observation_state("execution-1")
    apply_observed_frame(
        active,
        _frame("assistant.delta", sequence=1, payload={"content": "Resposta"}),
    )

    update = apply_observed_frame(
        active,
        _frame(
            "execution.phase.changed",
            sequence=2,
            payload={"phase": "finalizing"},
        ),
    )

    assert update.response_started is True
    assert active["response_started"] is True
    assert active["response_completed"] is True
    assert active["phase"] == "finalizing"


def test_execution_state_rehydrates_activities_and_live_tail_does_not_duplicate_them() -> None:
    active = new_observation_state("execution-1")
    state = _frame(
        "execution.state",
        sequence=2,
        payload={
            "status": "running",
            "phase": "tool",
            "realtime_available": True,
            "activities": [
                {
                    "sequence": 1,
                    "type": "context.loaded",
                    "payload": {"history_turns": 2},
                },
                {
                    "sequence": 2,
                    "type": "tool.started",
                    "payload": {
                        "tool": "database",
                        "tool_call_id": "call-1",
                        "arguments": {"action": "query", "sql": "SELECT 1"},
                    },
                },
            ],
        },
    )

    first = apply_observed_frame(active, state)
    duplicate = apply_observed_frame(
        active,
        _frame(
            "tool.started",
            sequence=2,
            payload={
                "tool": "database",
                "tool_call_id": "call-1",
                "arguments": {"action": "query", "sql": "SELECT 1"},
            },
        ),
    )

    assert len(first.new_activities) == 2
    assert duplicate.new_activities == ()
    assert len(active["activities"]) == 2
    assert active["activities"][1]["title"] == "Consultando o banco de dados"
    assert "SELECT 1" in str(active["activities"][1]["detail"])


def test_transport_frames_never_pollute_agent_activity_timeline() -> None:
    active = new_observation_state("execution-1")

    heartbeat = apply_observed_frame(active, _frame("heartbeat", sequence=None))
    degraded = apply_observed_frame(
        active,
        _frame(
            "execution.realtime_unavailable",
            sequence=None,
            payload={"reason": "stream_unavailable"},
        ),
    )

    assert classify_frame(_frame("heartbeat", sequence=None)) == FrameKind.TRANSPORT
    assert heartbeat.new_activities == ()
    assert degraded.transport_degraded is True
    assert degraded.new_activities == ()
    assert active["activities"] == []


def test_completed_event_is_terminal_and_preserves_final_answer() -> None:
    active = new_observation_state("execution-1")
    apply_observed_frame(
        active,
        _frame("assistant.delta", sequence=1, payload={"content": "Parcial"}),
    )

    update = apply_observed_frame(
        active,
        _frame(
            "execution.completed",
            sequence=2,
            payload={"answer": "Resposta final", "result": {"rows": 5}},
        ),
    )

    assert update.kind == FrameKind.TERMINAL
    assert update.terminal_status == "completed"
    assert active["content"] == "Resposta final"
    assert active["result"] == {"rows": 5}
    assert active["response_started"] is True
    assert active["response_completed"] is True
