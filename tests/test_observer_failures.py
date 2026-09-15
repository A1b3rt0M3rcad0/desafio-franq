import pytest

from package.agent.observer.observer import RedisExecutionObserver


class FailingHotState:
    async def get(self, execution_id: str):
        raise RuntimeError("redis unavailable")


class EmptyEventStream:
    async def latest(self, execution_id: str):
        return None


class DurableCompletedState:
    async def get(self, execution_id: str):
        return {
            "execution_id": execution_id,
            "session_id": "session-1",
            "status": "completed",
            "answer": "Resposta durável",
            "error": None,
            "result": {"iterations": 2},
        }


@pytest.mark.asyncio
async def test_realtime_failure_falls_back_to_durable_execution_state() -> None:
    observer = RedisExecutionObserver(
        hot_state=FailingHotState(),
        event_stream=EmptyEventStream(),
        durable_state=DurableCompletedState(),
        acceptance_poll_seconds=0.001,
        projection_max_activities=20,
    )

    frame = await observer.current_state("execution-1")

    assert frame.payload["status"] == "completed"
    assert frame.payload["answer"] == "Resposta durável"
    assert frame.payload["realtime_available"] is False
    assert frame.payload["realtime_reason"] == "hot_state_unavailable"
