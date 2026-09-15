import asyncio
import logging
from contextlib import suppress

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from package.agent.database.models.execution import ExecutionStatus
from package.agent.database.models.outbox import OutboxMessage
from package.agent.database.repositories.executions import ExecutionRepository
from package.agent.database.repositories.outbox import OutboxRepository
from package.agent.llm.errors import LLMProviderError
from package.agent.observer.contracts import ExecutionEventSink
from package.agent.observer.events import ExecutionEvent, ExecutionEventType
from package.runner.contracts import RuntimeFactory
from package.runner.runtime.health import RunnerHealthReporter
from package.runner.runtime.retry import OutboxRetryPolicy


logger = logging.getLogger(__name__)


class ExecutionConsumer:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        runtime_factory: RuntimeFactory,
        runner_id: str,
        batch_size: int,
        max_attempts: int,
        cancellation_poll_seconds: float,
        retry_policy: OutboxRetryPolicy,
        health_reporter: RunnerHealthReporter,
        event_sink: ExecutionEventSink | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be greater than zero")
        if cancellation_poll_seconds <= 0:
            raise ValueError("cancellation_poll_seconds must be greater than zero")
        self._session_factory = session_factory
        self._runtime_factory = runtime_factory
        self._runner_id = runner_id
        self._batch_size = batch_size
        self._max_attempts = max_attempts
        self._cancellation_poll_seconds = cancellation_poll_seconds
        self._retry_policy = retry_policy
        self._health_reporter = health_reporter
        self._event_sink = event_sink

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

            if execution.status == ExecutionStatus.CANCEL_REQUESTED.value:
                await execution_repo.mark_cancelled(execution)
                persisted_message = await db.get(OutboxMessage, message.id)
                if persisted_message is not None:
                    await OutboxRepository(db).mark_processed(persisted_message)
                await db.commit()
                await self._emit_lifecycle(
                    execution_id,
                    ExecutionEventType.EXECUTION_CANCELLED,
                    {"reason": "user_requested"},
                )
                return

            await execution_repo.mark_running(execution)
            await db.commit()

        await self._emit_lifecycle(
            execution_id,
            ExecutionEventType.EXECUTION_STARTED,
            {"session_id": session_id},
        )

        try:
            runtime = self._runtime_factory.create()
            runtime_task = asyncio.create_task(
                runtime.run(
                    execution_id=execution_id,
                    session_id=session_id,
                    question=question,
                )
            )
            cancellation_task = asyncio.create_task(
                self._wait_for_cancellation(execution_id)
            )

            done, _ = await asyncio.wait(
                {runtime_task, cancellation_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if cancellation_task in done and cancellation_task.result():
                runtime_task.cancel()
                with suppress(asyncio.CancelledError):
                    await runtime_task
                await self._mark_cancelled(
                    execution_id=execution_id,
                    message_id=message.id,
                )
                return

            cancellation_task.cancel()
            with suppress(asyncio.CancelledError):
                await cancellation_task
            result = await runtime_task
        except asyncio.CancelledError:
            await self._mark_cancelled(
                execution_id=execution_id,
                message_id=message.id,
            )
            return
        except Exception as exc:
            logger.exception("Execution %s failed in the runner", execution_id)
            if await self._is_cancel_requested(execution_id):
                await self._mark_cancelled(
                    execution_id=execution_id,
                    message_id=message.id,
                )
                return
            if isinstance(exc, LLMProviderError) and not exc.retryable:
                await self._health_reporter.mark_unavailable(
                    provider=exc.provider,
                    model=exc.model,
                    error=str(exc),
                )
            internal_error = str(exc) or exc.__class__.__name__
            await self._mark_terminal_failure(
                execution_id=execution_id,
                message_id=message.id,
                error=_public_execution_error(exc),
                internal_error=internal_error,
            )
            return

        terminal_type = ExecutionEventType.EXECUTION_COMPLETED
        terminal_payload = {"answer": result.answer, "result": result.result}
        async with self._session_factory() as db:
            execution_repo = ExecutionRepository(db)
            execution = await execution_repo.get(execution_id)
            if execution is not None:
                if execution.status == ExecutionStatus.CANCEL_REQUESTED.value:
                    await execution_repo.mark_cancelled(execution, answer=result.answer)
                    terminal_type = ExecutionEventType.EXECUTION_CANCELLED
                    terminal_payload = {
                        "reason": "user_requested",
                        "partial_answer": result.answer,
                    }
                else:
                    await execution_repo.mark_completed(
                        execution,
                        answer=result.answer,
                        result=result.result,
                    )
            persisted_message = await db.get(OutboxMessage, message.id)
            if persisted_message is not None:
                await OutboxRepository(db).mark_processed(persisted_message)
            await db.commit()

        await self._emit_lifecycle(execution_id, terminal_type, terminal_payload)

    async def _wait_for_cancellation(self, execution_id: str) -> bool:
        while True:
            await asyncio.sleep(self._cancellation_poll_seconds)
            async with self._session_factory() as db:
                execution = await ExecutionRepository(db).get(execution_id)
                if execution is None:
                    return False
                if execution.status in {
                    ExecutionStatus.CANCEL_REQUESTED.value,
                    ExecutionStatus.CANCELLED.value,
                }:
                    return True
                if execution.status in {
                    ExecutionStatus.COMPLETED.value,
                    ExecutionStatus.FAILED.value,
                }:
                    return False

    async def _is_cancel_requested(self, execution_id: str) -> bool:
        async with self._session_factory() as db:
            execution = await ExecutionRepository(db).get(execution_id)
            if execution is None:
                return False
            return execution.status in {
                ExecutionStatus.CANCEL_REQUESTED.value,
                ExecutionStatus.CANCELLED.value,
            }

    async def _mark_cancelled(
        self,
        *,
        execution_id: str,
        message_id: str,
    ) -> None:
        async with self._session_factory() as db:
            execution_repo = ExecutionRepository(db)
            execution = await execution_repo.get(execution_id)
            if execution is not None:
                await execution_repo.mark_cancelled(execution)
            persisted_message = await db.get(OutboxMessage, message_id)
            if persisted_message is not None:
                await OutboxRepository(db).mark_processed(persisted_message)
            await db.commit()
        await self._emit_lifecycle(
            execution_id,
            ExecutionEventType.EXECUTION_CANCELLED,
            {"reason": "user_requested"},
        )

    async def _mark_terminal_failure(
        self,
        *,
        execution_id: str,
        message_id: str,
        error: str,
        internal_error: str | None = None,
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
                    error=internal_error or error,
                )
            await db.commit()
        await self._emit_lifecycle(
            execution_id,
            ExecutionEventType.EXECUTION_FAILED,
            {"error": error},
        )

    async def _mark_processed(self, message_id: str) -> None:
        async with self._session_factory() as db:
            message = await db.get(OutboxMessage, message_id)
            if message is not None:
                await OutboxRepository(db).mark_processed(message)
                await db.commit()

    async def _emit_lifecycle(
        self,
        execution_id: str,
        event_type: ExecutionEventType,
        payload: dict,
    ) -> None:
        if self._event_sink is None:
            return
        try:
            await self._event_sink.emit(
                ExecutionEvent(
                    execution_id=execution_id,
                    type=event_type,
                    payload=payload,
                )
            )
        except Exception:
            logger.exception(
                "Failed to publish lifecycle event %s for execution %s",
                event_type.value,
                execution_id,
            )


def _public_execution_error(exc: Exception) -> str:
    if isinstance(exc, SQLAlchemyError):
        return "Falha interna de persistência durante a execução."
    return str(exc) or exc.__class__.__name__
