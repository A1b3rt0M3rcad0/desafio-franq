import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse

from package.agent.cache.event_stream import ExecutionEventStream
from package.api.http.dependencies import get_event_stream

router = APIRouter(prefix="/executions", tags=["events"])


@router.get("/{execution_id}/events")
async def stream_execution_events(
    execution_id: str,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    stream: ExecutionEventStream = Depends(get_event_stream),
) -> StreamingResponse:
    async def event_source() -> AsyncIterator[str]:
        cursor = last_event_id or "0-0"
        while True:
            events = await stream.read(execution_id, after=cursor)
            if not events:
                yield ": keep-alive\n\n"
                continue

            for event in events:
                cursor = event.stream_id
                data = json.dumps(
                    {
                        "sequence": event.sequence,
                        "type": event.event_type,
                        "payload": event.payload,
                    },
                    ensure_ascii=False,
                )
                yield (
                    f"id: {event.stream_id}\n"
                    f"event: {event.event_type}\n"
                    f"data: {data}\n\n"
                )

                if event.event_type in {"execution.completed", "execution.failed"}:
                    return

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
