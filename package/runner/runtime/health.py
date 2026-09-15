from package.agent.cache.runner_health import (
    RunnerHealthStatus,
    RunnerHealthStore,
)
from package.runner.runtime.lifecycle import ShutdownSignal


class RunnerHealthReporter:
    def __init__(
        self,
        *,
        store: RunnerHealthStore,
        runner_id: str,
        heartbeat_seconds: float,
    ) -> None:
        if heartbeat_seconds <= 0:
            raise ValueError("runner health heartbeat must be greater than zero")
        self._store = store
        self._runner_id = runner_id
        self._heartbeat_seconds = heartbeat_seconds
        self._status = RunnerHealthStatus.UNAVAILABLE
        self._provider = "unknown"
        self._model: str | None = None
        self._error: str | None = "Runner is starting"

    async def mark_ready(self, *, provider: str, model: str) -> None:
        self._status = RunnerHealthStatus.READY
        self._provider = provider
        self._model = model
        self._error = None
        await self._publish()

    async def mark_unavailable(
        self,
        *,
        provider: str,
        model: str | None,
        error: str,
    ) -> None:
        self._status = RunnerHealthStatus.UNAVAILABLE
        self._provider = provider
        self._model = model
        self._error = error
        await self._publish()

    async def run(self, shutdown: ShutdownSignal) -> None:
        while not shutdown.requested:
            await self._publish()
            await shutdown.wait(self._heartbeat_seconds)

    async def clear(self) -> None:
        await self._store.clear(self._runner_id)

    async def _publish(self) -> None:
        await self._store.publish(
            runner_id=self._runner_id,
            status=self._status,
            provider=self._provider,
            model=self._model,
            error=self._error,
        )
