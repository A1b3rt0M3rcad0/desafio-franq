import json
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis


@dataclass(frozen=True, slots=True)
class StreamEvent:
    stream_id: str
    sequence: int
    event_type: str
    payload: dict[str, Any]


class ExecutionEventStream:
    def __init__(
        self,
        redis: Redis,
        *,
        maxlen: int = 5_000,
        ttl_seconds: int = 21_600,
    ) -> None:
        self._redis = redis
        self._maxlen = maxlen
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def _stream_key(execution_id: str) -> str:
        return f"execution:{execution_id}:events"

    @staticmethod
    def _sequence_key(execution_id: str) -> str:
        return f"execution:{execution_id}:sequence"

    async def append(
        self,
        *,
        execution_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> StreamEvent:
        sequence = int(await self._redis.incr(self._sequence_key(execution_id)))
        stream_id = await self._redis.xadd(
            self._stream_key(execution_id),
            {
                "sequence": str(sequence),
                "type": event_type,
                "payload": json.dumps(payload, ensure_ascii=False, default=str),
            },
            maxlen=self._maxlen,
            approximate=True,
        )
        return StreamEvent(
            stream_id=str(stream_id),
            sequence=sequence,
            event_type=event_type,
            payload=payload,
        )

    async def read(
        self,
        execution_id: str,
        *,
        after: str = "0-0",
        block_ms: int = 15_000,
        count: int = 100,
    ) -> list[StreamEvent]:
        result = await self._redis.xread(
            {self._stream_key(execution_id): after},
            count=count,
            block=block_ms,
        )
        events: list[StreamEvent] = []
        for _stream, messages in result:
            for stream_id, fields in messages:
                events.append(
                    StreamEvent(
                        stream_id=str(stream_id),
                        sequence=int(fields["sequence"]),
                        event_type=fields["type"],
                        payload=json.loads(fields["payload"]),
                    )
                )
        return events

    async def expire(self, execution_id: str) -> None:
        await self._redis.expire(self._stream_key(execution_id), self._ttl_seconds)
        await self._redis.expire(self._sequence_key(execution_id), self._ttl_seconds)
