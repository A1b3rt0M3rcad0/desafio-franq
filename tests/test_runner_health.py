from fnmatch import fnmatch

import pytest

from package.agent.cache.runner_health import RunnerHealthStatus, RunnerHealthStore


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    async def set(self, key: str, value: str, *, ex: int) -> None:
        self.values[key] = value
        self.expirations[key] = ex

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)
        self.expirations.pop(key, None)

    async def scan_iter(self, *, match: str):
        for key in list(self.values):
            if fnmatch(key, match):
                yield key


@pytest.mark.asyncio
async def test_runner_health_requires_at_least_one_ready_runner() -> None:
    redis = FakeRedis()
    store = RunnerHealthStore(redis, key_prefix="franq", ttl_seconds=15)

    await store.publish(
        runner_id="runner-1",
        status=RunnerHealthStatus.UNAVAILABLE,
        provider="openai",
        error="missing api key",
    )

    assert await store.any_ready() is False

    await store.publish(
        runner_id="runner-2",
        status=RunnerHealthStatus.READY,
        provider="deepseek",
        model="deepseek-test",
    )

    assert await store.any_ready() is True
    snapshots = await store.list()
    assert {snapshot.runner_id for snapshot in snapshots} == {"runner-1", "runner-2"}
    assert redis.expirations["franq:runner:runner-2:health"] == 15


@pytest.mark.asyncio
async def test_runner_health_disappears_when_runner_is_cleared() -> None:
    redis = FakeRedis()
    store = RunnerHealthStore(redis, key_prefix="franq", ttl_seconds=15)
    await store.publish(
        runner_id="runner-1",
        status=RunnerHealthStatus.READY,
        provider="openai",
        model="model-test",
    )

    await store.clear("runner-1")

    assert await store.any_ready() is False


@pytest.mark.asyncio
async def test_runner_health_ignores_corrupted_entries() -> None:
    redis = FakeRedis()
    redis.values["franq:runner:broken:health"] = "not-json"
    store = RunnerHealthStore(redis, key_prefix="franq", ttl_seconds=15)

    assert await store.list() == []
    assert await store.any_ready() is False
