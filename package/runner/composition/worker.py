from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from package.runner.consumers.execution import ExecutionConsumer
from package.runner.contracts import RuntimeFactory
from package.runner.runtime.lifecycle import ShutdownSignal
from package.runner.runtime.worker import Worker


def compose_worker(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    runtime_factory: RuntimeFactory,
    runner_id: str,
    batch_size: int,
    poll_interval_seconds: float,
    shutdown: ShutdownSignal,
) -> Worker:
    consumer = ExecutionConsumer(
        session_factory=session_factory,
        runtime_factory=runtime_factory,
        runner_id=runner_id,
        batch_size=batch_size,
    )
    return Worker(
        consumer=consumer,
        shutdown=shutdown,
        poll_interval_seconds=poll_interval_seconds,
    )
