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
        key_prefix: str,
        maxlen: int,
        ttl_seconds: int,
        read_block_ms: int,
        read_count: int,
    ) -> None:
        normalized_prefix = key_prefix.strip(":")
        if not normalized_prefix:
            raise ValueError("Redis key prefix cannot be empty")
        self._redis = redis
        self._key_prefix = normalized_prefix
        self._maxlen = maxlen
        self._ttl_seconds = ttl_seconds
        self._read_block_ms = read_block_ms
        self._read_count = read_count

    def _stream_key(self, execution_id: str) -> str:
        return f"{self._key_prefix}:execution:{execution_id}:events"

    def _sequence_key(self, execution_id: str) -> str:
        return f"{self._key_prefix}:execution:{execution_id}:sequence"

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
    ) -> list[StreamEvent]:
        result = await self._redis.xread(
            {self._stream_key(execution_id): after},
            count=self._read_count,
            block=self._read_block_ms,
        )
        events: list[StreamEvent] = []
        for _stream, messages in result:
            events.extend(self._decode_messages(messages))
        return events

    async def retained(self, execution_id: str) -> list[StreamEvent]:
        messages = await self._redis.xrange(
            self._stream_key(execution_id),
            min="-",
            max="+",
            count=self._maxlen,
        )
        return self._decode_messages(messages)

    async def latest(self, execution_id: str) -> StreamEvent | None:
        messages = await self._redis.xrevrange(
            self._stream_key(execution_id),
            max="+",
            min="-",
            count=1,
        )
        decoded = self._decode_messages(messages)
        return decoded[0] if decoded else None

    async def expire(self, execution_id: str) -> None:
        await self._redis.expire(self._stream_key(execution_id), self._ttl_seconds)
        await self._redis.expire(self._sequence_key(execution_id), self._ttl_seconds)

    @staticmethod
    def _decode_messages(messages: list[tuple[str, dict[str, str]]]) -> list[StreamEvent]:
        return [
            StreamEvent(
                stream_id=str(stream_id),
                sequence=int(fields["sequence"]),
                event_type=fields["type"],
                payload=json.loads(fields["payload"]),
            )
            for stream_id, fields in messages
        ]
