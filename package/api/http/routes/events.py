import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse

from package.agent.observer.frames import ExecutionFrame
from package.agent.observer.observer import RedisExecutionObserver
from package.api.http.dependencies import get_execution_observer

router = APIRouter(prefix="/executions", tags=["events"])


@router.get("/{execution_id}/events")
async def stream_execution_events(
    execution_id: str,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    observer: RedisExecutionObserver = Depends(get_execution_observer),
) -> StreamingResponse:
    last_sequence = _parse_last_sequence(last_event_id)
    try:
        await observer.current_state(execution_id, last_sequence=last_sequence)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Execution not found") from exc

    async def event_source() -> AsyncIterator[str]:
        async for frame in observer.observe(
            execution_id,
            last_sequence=last_sequence,
        ):
            yield _format_sse(frame)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _parse_last_sequence(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        sequence = int(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Last-Event-ID must be a logical sequence",
        ) from exc
    if sequence < 0:
        raise HTTPException(status_code=400, detail="Last-Event-ID must be non-negative")
    return sequence


def _format_sse(frame: ExecutionFrame) -> str:
    data = json.dumps(frame.model_dump(mode="json"), ensure_ascii=False)
    event_id = f"id: {frame.sequence}\n" if frame.sequence is not None else ""
    return f"{event_id}event: {frame.type}\ndata: {data}\n\n"
