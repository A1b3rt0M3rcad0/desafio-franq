from typing import Any

from package.agent.cache.event_stream import ExecutionEventStream
from package.agent.cache.execution_state import ExecutionHotState
from package.agent.observer.events import ExecutionEvent, ExecutionEventType
from package.agent.trace.collector import TracePolicy
from package.agent.trace.recorder import TraceRecorder


class RedisExecutionObserver:
    """Publishes runtime events without making the runtime aware of Redis or persistence."""

    def __init__(
        self,
        *,
        hot_state: ExecutionHotState,
        event_stream: ExecutionEventStream,
        trace_recorder: TraceRecorder | None = None,
        trace_policy: TracePolicy | None = None,
    ) -> None:
        self._hot_state = hot_state
        self._event_stream = event_stream
        self._trace_recorder = trace_recorder
        self._trace_policy = trace_policy or TracePolicy()
        self._partial_answers: dict[str, str] = {}

    async def emit(self, event: ExecutionEvent) -> None:
        stream_event = await self._event_stream.append(
            execution_id=event.execution_id,
            event_type=event.type.value,
            payload={**event.payload, "created_at": event.created_at.isoformat()},
        )

        await self._update_hot_state(event, sequence=stream_event.sequence)

        if self._trace_recorder is not None and self._trace_policy.should_record(event):
            await self._trace_recorder.record(event, sequence=stream_event.sequence)

        if event.type in {
            ExecutionEventType.EXECUTION_COMPLETED,
            ExecutionEventType.EXECUTION_FAILED,
        }:
            self._partial_answers.pop(event.execution_id, None)
            await self._hot_state.expire(event.execution_id)
            await self._event_stream.expire(event.execution_id)

    async def _update_hot_state(self, event: ExecutionEvent, *, sequence: int) -> None:
        current = await self._hot_state.get(event.execution_id) or {}
        state: dict[str, Any] = {
            **current,
            "execution_id": event.execution_id,
            "last_sequence": sequence,
            "last_event": event.type.value,
            "updated_at": event.created_at.isoformat(),
        }

        if event.type == ExecutionEventType.EXECUTION_STARTED:
            state["status"] = "running"
        elif event.type == ExecutionEventType.ASSISTANT_DELTA:
            content = str(event.payload.get("content", ""))
            partial = self._partial_answers.get(event.execution_id, "") + content
            self._partial_answers[event.execution_id] = partial
            state["partial_answer"] = partial
        elif event.type == ExecutionEventType.EXECUTION_COMPLETED:
            state["status"] = "completed"
            state["answer"] = event.payload.get("answer")
        elif event.type == ExecutionEventType.EXECUTION_FAILED:
            state["status"] = "failed"
            state["error"] = event.payload.get("error")

        await self._hot_state.set(event.execution_id, state)
