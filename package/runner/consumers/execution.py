from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from package.agent.database.models.outbox import OutboxMessage
from package.agent.database.repositories.executions import ExecutionRepository
from package.agent.database.repositories.outbox import OutboxRepository
from package.agent.llm.errors import LLMProviderError
from package.runner.contracts import RuntimeFactory
from package.runner.runtime.health import RunnerHealthReporter
from package.runner.runtime.retry import OutboxRetryPolicy


class ExecutionConsumer:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        runtime_factory: RuntimeFactory,
        runner_id: str,
        batch_size: int,
        max_attempts: int,
        retry_policy: OutboxRetryPolicy,
        health_reporter: RunnerHealthReporter,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be greater than zero")
        self._session_factory = session_factory
        self._runtime_factory = runtime_factory
        self._runner_id = runner_id
        self._batch_size = batch_size
        self._max_attempts = max_attempts
        self._retry_policy = retry_policy
        self._health_reporter = health_reporter

    async def consume_once(self) -> int:
        async with self._session_factory() as db:
            outbox = OutboxRepository(db)
            messages = await outbox.claim_batch(
                runner_id=self._runner_id,
                limit=self._batch_size,
            )
            await db.commit()

        for message in messages:
            await self._handle_message(message)
        return len(messages)

    async def _handle_message(self, message: OutboxMessage) -> None:
        if message.event_type != "execution.requested":
            await self._mark_processed(message.id)
            return

        execution_id = str(message.payload["execution_id"])
        session_id = str(message.payload["session_id"])
        question = str(message.payload["question"])

        async with self._session_factory() as db:
            execution_repo = ExecutionRepository(db)
            execution = await execution_repo.get(execution_id)
            if execution is None:
                persisted_message = await db.get(OutboxMessage, message.id)
                if persisted_message is not None:
                    outbox = OutboxRepository(db)
                    if message.attempts >= self._max_attempts:
                        await outbox.mark_failed(
                            persisted_message,
                            error="Execution not found",
                        )
                    else:
                        await outbox.release_with_error(
                            persisted_message,
                            error="Execution not found",
                            retry_delay_seconds=self._retry_policy.delay(message.attempts),
                        )
                await db.commit()
                return
            await execution_repo.mark_running(execution)
            await db.commit()

        try:
            runtime = self._runtime_factory.create()
            result = await runtime.run(
                execution_id=execution_id,
                session_id=session_id,
                question=question,
            )
        except Exception as exc:
            if isinstance(exc, LLMProviderError) and not exc.retryable:
                await self._health_reporter.mark_unavailable(
                    provider=exc.provider,
                    model=exc.model,
                    error=str(exc),
                )
            await self._mark_terminal_failure(
                execution_id=execution_id,
                message_id=message.id,
                error=str(exc) or exc.__class__.__name__,
            )
            return

        async with self._session_factory() as db:
            execution_repo = ExecutionRepository(db)
            execution = await execution_repo.get(execution_id)
            if execution is not None:
                await execution_repo.mark_completed(
                    execution,
                    answer=result.answer,
                    result=result.result,
                )
            persisted_message = await db.get(OutboxMessage, message.id)
            if persisted_message is not None:
                await OutboxRepository(db).mark_processed(persisted_message)
            await db.commit()

    async def _mark_terminal_failure(
        self,
        *,
        execution_id: str,
        message_id: str,
        error: str,
    ) -> None:
        """A runtime failure is terminal for this Execution and must not loop."""
        async with self._session_factory() as db:
            execution_repo = ExecutionRepository(db)
            execution = await execution_repo.get(execution_id)
            if execution is not None:
                await execution_repo.mark_failed(execution, error)
            persisted_message = await db.get(OutboxMessage, message_id)
            if persisted_message is not None:
                await OutboxRepository(db).mark_failed(
                    persisted_message,
                    error=error,
                )
            await db.commit()

    async def _mark_processed(self, message_id: str) -> None:
        async with self._session_factory() as db:
            message = await db.get(OutboxMessage, message_id)
            if message is not None:
                await OutboxRepository(db).mark_processed(message)
                await db.commit()
