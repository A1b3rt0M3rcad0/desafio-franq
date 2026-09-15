import asyncio

from package.agent.cache.event_stream import ExecutionEventStream
from package.agent.cache.execution_state import ExecutionHotState
from package.agent.observer.events import ExecutionEvent, ExecutionEventType
from package.agent.observer.projection import initial_projection, public_event, reduce_projection
from package.agent.trace.collector import TracePolicy
from package.agent.trace.recorder import TraceRecorder


class RedisExecutionEventSink:
    """Projects runtime events to Redis and trace without owning execution lifecycle."""

    def __init__(
        self,
        *,
        hot_state: ExecutionHotState,
        event_stream: ExecutionEventStream,
        projection_max_activities: int,
        trace_recorder: TraceRecorder | None = None,
        trace_policy: TracePolicy | None = None,
    ) -> None:
        if projection_max_activities < 1:
            raise ValueError("projection_max_activities must be greater than zero")
        self._hot_state = hot_state
        self._event_stream = event_stream
        self._projection_max_activities = projection_max_activities
        self._trace_recorder = trace_recorder
        self._trace_policy = trace_policy or TracePolicy()
        self._locks: dict[str, asyncio.Lock] = {}

    async def emit(self, event: ExecutionEvent) -> None:
        lock = self._locks.setdefault(event.execution_id, asyncio.Lock())
        async with lock:
            event_type, payload = public_event(event)
            public_payload = {
                **payload,
                "created_at": event.created_at.isoformat(),
            }
            stream_event = await self._event_stream.append(
                execution_id=event.execution_id,
                event_type=event_type,
                payload=public_payload,
            )

            current = await self._hot_state.get(event.execution_id)
            projection = current or initial_projection(event.execution_id)
            projection = reduce_projection(
                projection,
                event_type=event_type,
                payload=public_payload,
                sequence=stream_event.sequence,
                max_activities=self._projection_max_activities,
            )
            await self._hot_state.set(event.execution_id, projection)

            if self._trace_recorder is not None and self._trace_policy.should_record(event):
                await self._trace_recorder.record(event, sequence=stream_event.sequence)

            if event.type in {
                ExecutionEventType.EXECUTION_COMPLETED,
                ExecutionEventType.EXECUTION_FAILED,
                ExecutionEventType.EXECUTION_CANCELLED,
            }:
                await self._hot_state.expire(event.execution_id)
                await self._event_stream.expire(event.execution_id)
                self._locks.pop(event.execution_id, None)
