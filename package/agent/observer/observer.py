import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from package.agent.cache.event_stream import ExecutionEventStream, StreamEvent
from package.agent.cache.execution_state import ExecutionHotState
from package.agent.observer.contracts import DurableExecutionStateReader
from package.agent.observer.frames import (
    EXECUTION_STATE_FRAME,
    HEARTBEAT_FRAME,
    REALTIME_UNAVAILABLE_FRAME,
    TERMINAL_EVENT_TYPES,
    TERMINAL_EXECUTION_STATUSES,
    ExecutionFrame,
)
from package.agent.observer.projection import (
    initial_projection,
    public_projection,
    reduce_projection,
)


class ExecutionObservationGapError(RuntimeError):
    """Raised when retained realtime events cannot bridge the saved projection."""


class RedisExecutionObserver:
    """Reconstruct current execution state and follow the lossless realtime tail."""

    def __init__(
        self,
        *,
        hot_state: ExecutionHotState,
        event_stream: ExecutionEventStream,
        durable_state: DurableExecutionStateReader,
        acceptance_poll_seconds: float,
        projection_max_activities: int,
    ) -> None:
        if acceptance_poll_seconds <= 0:
            raise ValueError("acceptance_poll_seconds must be greater than zero")
        if projection_max_activities < 1:
            raise ValueError("projection_max_activities must be greater than zero")
        self._hot_state = hot_state
        self._event_stream = event_stream
        self._durable_state = durable_state
        self._acceptance_poll_seconds = acceptance_poll_seconds
        self._projection_max_activities = projection_max_activities

    async def current_state(
        self,
        execution_id: str,
        *,
        last_sequence: int | None = None,
    ) -> ExecutionFrame:
        frame, _cursor = await self._resolve_current_state(
            execution_id,
            last_sequence=last_sequence,
        )
        return frame

    async def observe(
        self,
        execution_id: str,
        *,
        last_sequence: int | None = None,
    ) -> AsyncIterator[ExecutionFrame]:
        try:
            state_frame, cursor = await self._resolve_current_state(
                execution_id,
                last_sequence=last_sequence,
            )
        except ExecutionObservationGapError as exc:
            yield self._realtime_unavailable(execution_id, reason="sequence_gap", detail=str(exc))
            return

        yield state_frame
        if self._is_terminal_state(state_frame):
            return
        if cursor is None and state_frame.payload.get("realtime_reason") in {
            "hot_state_unavailable",
            "stream_unavailable",
        }:
            yield self._realtime_unavailable(
                execution_id,
                reason=str(state_frame.payload["realtime_reason"]),
                detail="Realtime observation is unavailable; durable state remains authoritative.",
            )
            return

        while cursor is None:
            await asyncio.sleep(self._acceptance_poll_seconds)
            try:
                candidate, cursor = await self._resolve_current_state(
                    execution_id,
                    last_sequence=state_frame.sequence,
                )
            except ExecutionObservationGapError as exc:
                yield self._realtime_unavailable(
                    execution_id,
                    reason="sequence_gap",
                    detail=str(exc),
                )
                return

            if self._is_terminal_state(candidate):
                yield candidate
                return
            if candidate.payload.get("realtime_reason") in {
                "hot_state_unavailable",
                "stream_unavailable",
            }:
                yield candidate
                yield self._realtime_unavailable(
                    execution_id,
                    reason=str(candidate.payload["realtime_reason"]),
                    detail=(
                        "Realtime observation is unavailable; durable state remains authoritative."
                    ),
                )
                return
            if candidate.payload.get("realtime_available"):
                state_frame = candidate
                yield state_frame
                break

        sequence = int(state_frame.sequence or 0)
        while cursor is not None:
            try:
                events = await self._event_stream.read(execution_id, after=cursor)
            except Exception as exc:
                yield self._realtime_unavailable(
                    execution_id,
                    reason="stream_unavailable",
                    detail=str(exc),
                )
                return

            if not events:
                yield ExecutionFrame(
                    execution_id=execution_id,
                    type=HEARTBEAT_FRAME,
                    payload={"timestamp": datetime.now(timezone.utc).isoformat()},
                )
                continue

            for event in events:
                cursor = event.stream_id
                if event.sequence <= sequence:
                    continue
                expected = sequence + 1
                if event.sequence != expected:
                    yield self._realtime_unavailable(
                        execution_id,
                        reason="sequence_gap",
                        detail=f"expected={expected} observed={event.sequence}",
                    )
                    return

                sequence = event.sequence
                frame = self._event_frame(execution_id, event)
                yield frame
                if event.event_type in TERMINAL_EVENT_TYPES:
                    return

    async def _resolve_current_state(
        self,
        execution_id: str,
        *,
        last_sequence: int | None,
    ) -> tuple[ExecutionFrame, str | None]:
        durable = await self._durable_state.get(execution_id)
        if durable is None:
            raise KeyError(execution_id)

        try:
            hot = await self._hot_state.get(execution_id)
        except Exception:
            projection = initial_projection(execution_id, durable)
            payload = public_projection(projection, realtime_available=False)
            payload["sequence"] = None
            payload["realtime_reason"] = "hot_state_unavailable"
            if last_sequence is not None:
                payload["reattached_from_sequence"] = last_sequence
            return (
                ExecutionFrame(
                    execution_id=execution_id,
                    type=EXECUTION_STATE_FRAME,
                    sequence=None,
                    payload=payload,
                ),
                None,
            )

        if hot is None:
            projection = initial_projection(execution_id, durable)
            payload = public_projection(projection, realtime_available=False)
            payload["sequence"] = None
            payload["realtime_reason"] = "awaiting_runtime"
            if last_sequence is not None:
                payload["reattached_from_sequence"] = last_sequence
            return (
                ExecutionFrame(
                    execution_id=execution_id,
                    type=EXECUTION_STATE_FRAME,
                    sequence=None,
                    payload=payload,
                ),
                None,
            )

        try:
            latest = await self._event_stream.latest(execution_id)
        except Exception:
            latest = None

        if latest is None:
            projection = {**initial_projection(execution_id, durable), **hot}
            payload = public_projection(projection, realtime_available=False)
            payload["realtime_reason"] = "stream_unavailable"
            sequence = _projection_sequence(projection) or None
            if last_sequence is not None:
                payload["reattached_from_sequence"] = last_sequence
            return (
                ExecutionFrame(
                    execution_id=execution_id,
                    type=EXECUTION_STATE_FRAME,
                    sequence=sequence,
                    payload=payload,
                ),
                None,
            )

        high_watermark = latest.sequence
        projection = {**initial_projection(execution_id, durable), **hot}
        projection_sequence = _projection_sequence(projection)

        if projection_sequence < high_watermark:
            try:
                retained = await self._event_stream.retained(execution_id)
            except Exception:
                payload = public_projection(projection, realtime_available=False)
                payload["realtime_reason"] = "stream_unavailable"
                return (
                    ExecutionFrame(
                        execution_id=execution_id,
                        type=EXECUTION_STATE_FRAME,
                        sequence=projection_sequence or None,
                        payload=payload,
                    ),
                    None,
                )
            relevant = [
                event
                for event in retained
                if projection_sequence < event.sequence <= high_watermark
            ]
            if not relevant or relevant[0].sequence != projection_sequence + 1:
                first = relevant[0].sequence if relevant else None
                raise ExecutionObservationGapError(
                    "retained history cannot bridge projection "
                    f"projection={projection_sequence} first={first} high={high_watermark}"
                )

            expected = projection_sequence + 1
            for event in relevant:
                if event.sequence != expected:
                    raise ExecutionObservationGapError(
                        f"expected={expected} observed={event.sequence}"
                    )
                projection = reduce_projection(
                    projection,
                    event_type=event.event_type,
                    payload=event.payload,
                    sequence=event.sequence,
                    max_activities=self._projection_max_activities,
                )
                expected += 1
            if relevant[-1].sequence != high_watermark:
                raise ExecutionObservationGapError(
                    f"projection stopped at {relevant[-1].sequence}, high={high_watermark}"
                )
        elif projection_sequence > high_watermark:
            payload = public_projection(projection, realtime_available=False)
            payload["realtime_reason"] = "stream_unavailable"
            if last_sequence is not None:
                payload["reattached_from_sequence"] = last_sequence
            return (
                ExecutionFrame(
                    execution_id=execution_id,
                    type=EXECUTION_STATE_FRAME,
                    sequence=projection_sequence,
                    payload=payload,
                ),
                None,
            )

        projection["sequence"] = high_watermark
        payload = public_projection(projection, realtime_available=True)
        if last_sequence is not None:
            payload["reattached_from_sequence"] = last_sequence
        return (
            ExecutionFrame(
                execution_id=execution_id,
                type=EXECUTION_STATE_FRAME,
                sequence=high_watermark,
                payload=payload,
            ),
            latest.stream_id,
        )

    @staticmethod
    def _event_frame(execution_id: str, event: StreamEvent) -> ExecutionFrame:
        return ExecutionFrame(
            execution_id=execution_id,
            type=event.event_type,
            sequence=event.sequence,
            payload={
                "execution_id": execution_id,
                "sequence": event.sequence,
                **event.payload,
            },
        )

    @staticmethod
    def _is_terminal_state(frame: ExecutionFrame) -> bool:
        return str(frame.payload.get("status") or "").lower() in TERMINAL_EXECUTION_STATUSES

    @staticmethod
    def _realtime_unavailable(
        execution_id: str,
        *,
        reason: str,
        detail: str,
    ) -> ExecutionFrame:
        return ExecutionFrame(
            execution_id=execution_id,
            type=REALTIME_UNAVAILABLE_FRAME,
            payload={
                "execution_id": execution_id,
                "reason": reason,
                "detail": detail,
                "realtime_available": False,
            },
        )


def _projection_sequence(projection: dict[str, object]) -> int:
    raw = projection.get("sequence")
    if isinstance(raw, int) and not isinstance(raw, bool):
        return max(0, raw)
    legacy = projection.get("last_sequence")
    if isinstance(legacy, int) and not isinstance(legacy, bool):
        return max(0, legacy)
    return 0
