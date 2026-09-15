from package.runner.consumers.execution import ExecutionConsumer
from package.runner.runtime.lifecycle import ShutdownSignal


class Worker:
    def __init__(
        self,
        *,
        consumer: ExecutionConsumer,
        shutdown: ShutdownSignal,
        poll_interval_seconds: float,
    ) -> None:
        self._consumer = consumer
        self._shutdown = shutdown
        self._poll_interval_seconds = poll_interval_seconds

    async def run(self) -> None:
        while not self._shutdown.requested:
            consumed = await self._consumer.consume_once()
            if consumed == 0:
                await self._shutdown.wait(self._poll_interval_seconds)
