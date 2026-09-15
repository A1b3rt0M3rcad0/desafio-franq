import json
from typing import Any

from redis.asyncio import Redis


class ExecutionHotState:
    def __init__(self, redis: Redis, *, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def _key(execution_id: str) -> str:
        return f"execution:{execution_id}:state"

    async def set(self, execution_id: str, state: dict[str, Any]) -> None:
        await self._redis.set(
            self._key(execution_id),
            json.dumps(state, ensure_ascii=False, default=str),
            ex=self._ttl_seconds,
        )

    async def get(self, execution_id: str) -> dict[str, Any] | None:
        raw = await self._redis.get(self._key(execution_id))
        if raw is None:
            return None
        return json.loads(raw)

    async def expire(self, execution_id: str) -> None:
        await self._redis.expire(self._key(execution_id), self._ttl_seconds)
