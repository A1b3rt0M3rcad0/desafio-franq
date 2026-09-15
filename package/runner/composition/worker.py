from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from package.runner.consumers.execution import ExecutionConsumer
from package.runner.contracts import RuntimeFactory
from package.runner.runtime.health import RunnerHealthReporter
from package.runner.runtime.lifecycle import ShutdownSignal
from package.runner.runtime.retry import OutboxRetryPolicy
from package.runner.runtime.worker import Worker


def compose_worker(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    runtime_factory: RuntimeFactory,
    runner_id: str,
    batch_size: int,
    max_attempts: int,
    poll_interval_seconds: float,
    cancellation_poll_seconds: float,
    retry_base_delay_seconds: float,
    retry_max_delay_seconds: float,
    retry_exponent_cap: int,
    health_reporter: RunnerHealthReporter,
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
        max_attempts=max_attempts,
        cancellation_poll_seconds=cancellation_poll_seconds,
        retry_policy=retry_policy,
        health_reporter=health_reporter,
    )
    return Worker(
        consumer=consumer,
        shutdown=shutdown,
        poll_interval_seconds=poll_interval_seconds,
    )
