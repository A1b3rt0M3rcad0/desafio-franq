from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from package.runner.consumers.execution import ExecutionConsumer
from package.runner.contracts import RuntimeFactory
from package.runner.runtime.lifecycle import ShutdownSignal
from package.runner.runtime.retry import OutboxRetryPolicy
from package.runner.runtime.worker import Worker


def compose_worker(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    runtime_factory: RuntimeFactory,
    runner_id: str,
    batch_size: int,
    poll_interval_seconds: float,
    retry_base_delay_seconds: float,
    retry_max_delay_seconds: float,
    retry_exponent_cap: int,
    shutdown: ShutdownSignal,
) -> Worker:
    retry_policy = OutboxRetryPolicy(
        base_delay_seconds=retry_base_delay_seconds,
        max_delay_seconds=retry_max_delay_seconds,
        exponent_cap=retry_exponent_cap,
    )
    consumer = ExecutionConsumer(
        session_factory=session_factory,
        runtime_factory=runtime_factory,
        runner_id=runner_id,
        batch_size=batch_size,
        retry_policy=retry_policy,
    )
    return Worker(
        consumer=consumer,
        shutdown=shutdown,
        poll_interval_seconds=poll_interval_seconds,
    )
