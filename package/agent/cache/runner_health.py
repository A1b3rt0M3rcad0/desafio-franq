import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum

from redis.asyncio import Redis


class RunnerHealthStatus(StrEnum):
    READY = "ready"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class RunnerHealthSnapshot:
    runner_id: str
    status: RunnerHealthStatus
    provider: str
    model: str | None
    error: str | None
    updated_at: str


class RunnerHealthStore:
    """Ephemeral Runner/provider availability shared between Runner and API."""

    def __init__(
        self,
        redis: Redis,
        *,
        key_prefix: str,
        ttl_seconds: int,
    ) -> None:
        normalized_prefix = key_prefix.strip(":")
        if not normalized_prefix:
            raise ValueError("Redis key prefix cannot be empty")
        if ttl_seconds < 1:
            raise ValueError("runner health ttl must be greater than zero")
        self._redis = redis
        self._key_prefix = normalized_prefix
        self._ttl_seconds = ttl_seconds

    def _key(self, runner_id: str) -> str:
        return f"{self._key_prefix}:runner:{runner_id}:health"

    def _pattern(self) -> str:
        return f"{self._key_prefix}:runner:*:health"

    async def publish(
        self,
        *,
        runner_id: str,
        status: RunnerHealthStatus,
        provider: str,
        model: str | None = None,
        error: str | None = None,
    ) -> RunnerHealthSnapshot:
        snapshot = RunnerHealthSnapshot(
            runner_id=runner_id,
            status=status,
            provider=provider,
            model=model,
            error=error[:500] if error else None,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        payload = asdict(snapshot)
        payload["status"] = snapshot.status.value
        await self._redis.set(
            self._key(runner_id),
            json.dumps(payload, ensure_ascii=False),
            ex=self._ttl_seconds,
        )
        return snapshot

    async def clear(self, runner_id: str) -> None:
        await self._redis.delete(self._key(runner_id))

    async def list(self) -> list[RunnerHealthSnapshot]:
        snapshots: list[RunnerHealthSnapshot] = []
        async for key in self._redis.scan_iter(match=self._pattern()):
            raw = await self._redis.get(key)
            if not raw:
                continue
            try:
                payload = json.loads(raw)
                snapshots.append(
                    RunnerHealthSnapshot(
                        runner_id=str(payload["runner_id"]),
                        status=RunnerHealthStatus(str(payload["status"])),
                        provider=str(payload["provider"]),
                        model=str(payload["model"]) if payload.get("model") else None,
                        error=str(payload["error"]) if payload.get("error") else None,
                        updated_at=str(payload["updated_at"]),
                    )
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return snapshots

    async def any_ready(self) -> bool:
        return any(
            snapshot.status == RunnerHealthStatus.READY
            for snapshot in await self.list()
        )
