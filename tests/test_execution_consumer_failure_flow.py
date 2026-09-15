from types import SimpleNamespace

import pytest

import package.runner.consumers.execution as execution_module
from package.agent.llm.errors import LLMProviderError
from package.runner.consumers.execution import ExecutionConsumer
from package.runner.runtime.retry import OutboxRetryPolicy
from package.runner.runtime.unavailable import AgentUnavailableError


class State:
    def __init__(self) -> None:
        self.execution = SimpleNamespace(id="execution-1", status="pending")
        self.outbox = SimpleNamespace(id="message-1", status="processing")
        self.actions: list[tuple] = []


class FakeSession:
    def __init__(self, state: State) -> None:
        self.state = state

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def commit(self) -> None:
        self.state.actions.append(("commit",))

    async def get(self, model, object_id: str):
        del model
        if object_id == self.state.outbox.id:
            return self.state.outbox
        return None


class FakeSessionFactory:
    def __init__(self, state: State) -> None:
        self.state = state

    def __call__(self) -> FakeSession:
        return FakeSession(self.state)


class FakeExecutionRepository:
    def __init__(self, db: FakeSession) -> None:
        self.state = db.state

    async def get(self, execution_id: str):
        if self.state.execution is None:
            return None
        return self.state.execution if execution_id == self.state.execution.id else None

    async def mark_running(self, execution) -> None:
        execution.status = "running"
        self.state.actions.append(("execution_running", execution.id))

    async def mark_failed(self, execution, error: str) -> None:
        execution.status = "failed"
        execution.error = error
        self.state.actions.append(("execution_failed", execution.id, error))

    async def mark_completed(self, execution, *, answer: str, result: dict) -> None:
        execution.status = "completed"
        execution.answer = answer
        execution.result = result
        self.state.actions.append(("execution_completed", execution.id, answer, result))


class FakeOutboxRepository:
    def __init__(self, db: FakeSession) -> None:
        self.state = db.state

    async def mark_processed(self, message) -> None:
        message.status = "processed"
        self.state.actions.append(("outbox_processed", message.id))

    async def mark_failed(self, message, *, error: str) -> None:
        message.status = "failed"
        message.error = error
        self.state.actions.append(("outbox_failed", message.id, error))

    async def release_with_error(
        self,
        message,
        *,
        error: str,
        retry_delay_seconds: float,
    ) -> None:
        message.status = "pending"
        message.error = error
        self.state.actions.append(
            ("outbox_released", message.id, error, retry_delay_seconds)
        )


class FakeHealthReporter:
    def __init__(self) -> None:
        self.unavailable: list[dict[str, object]] = []

    async def mark_unavailable(
        self,
        *,
        provider: str,
        model: str | None,
        error: str,
    ) -> None:
        self.unavailable.append(
            {"provider": provider, "model": model, "error": error}
        )


class FakeRuntime:
    def __init__(self, *, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    async def run(self, *, execution_id: str, session_id: str, question: str):
        del execution_id, session_id, question
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


class FakeRuntimeFactory:
    def __init__(self, *, runtime: FakeRuntime | None = None, error: Exception | None = None):
        self.runtime = runtime
        self.error = error
        self.calls = 0

    def create(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.runtime is not None
        return self.runtime


def _message(*, event_type: str = "execution.requested", attempts: int = 1):
    return SimpleNamespace(
        id="message-1",
        event_type=event_type,
        attempts=attempts,
        payload={
            "execution_id": "execution-1",
            "session_id": "session-1",
            "question": "pergunta",
        },
    )


def _consumer(
    state: State,
    runtime_factory,
    health: FakeHealthReporter,
    *,
    max_attempts: int = 3,
) -> ExecutionConsumer:
    return ExecutionConsumer(
        session_factory=FakeSessionFactory(state),
        runtime_factory=runtime_factory,
        runner_id="runner-1",
        batch_size=10,
        max_attempts=max_attempts,
        retry_policy=OutboxRetryPolicy(
            base_delay_seconds=2.0,
            max_delay_seconds=60.0,
            exponent_cap=5,
        ),
        health_reporter=health,
    )


@pytest.fixture(autouse=True)
def _replace_repositories(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(execution_module, "ExecutionRepository", FakeExecutionRepository)
    monkeypatch.setattr(execution_module, "OutboxRepository", FakeOutboxRepository)


@pytest.mark.asyncio
async def test_non_execution_outbox_message_is_acknowledged_without_runtime() -> None:
    state = State()
    health = FakeHealthReporter()
    factory = FakeRuntimeFactory(error=AssertionError("runtime must not be created"))
    consumer = _consumer(state, factory, health)

    await consumer._handle_message(_message(event_type="other.event"))

    assert ("outbox_processed", "message-1") in state.actions
    assert factory.calls == 0


@pytest.mark.asyncio
async def test_missing_execution_is_released_for_bounded_retry() -> None:
    state = State()
    state.execution = None
    health = FakeHealthReporter()
    consumer = _consumer(state, FakeRuntimeFactory(error=AssertionError()), health)

    await consumer._handle_message(_message(attempts=1))

    assert ("outbox_released", "message-1", "Execution not found", 2.0) in state.actions
    assert not any(action[0] == "outbox_failed" for action in state.actions)


@pytest.mark.asyncio
async def test_missing_execution_stops_retrying_at_max_attempts() -> None:
    state = State()
    state.execution = None
    health = FakeHealthReporter()
    consumer = _consumer(
        state,
        FakeRuntimeFactory(error=AssertionError()),
        health,
        max_attempts=3,
    )

    await consumer._handle_message(_message(attempts=3))

    assert ("outbox_failed", "message-1", "Execution not found") in state.actions
    assert not any(action[0] == "outbox_released" for action in state.actions)


@pytest.mark.asyncio
async def test_runtime_factory_startup_failure_is_terminal_and_never_requeued() -> None:
    state = State()
    health = FakeHealthReporter()
    factory = FakeRuntimeFactory(error=AgentUnavailableError("provider offline"))
    consumer = _consumer(state, factory, health)

    await consumer._handle_message(_message())

    assert state.execution.status == "failed"
    assert state.outbox.status == "failed"
    assert ("execution_failed", "execution-1", "provider offline") in state.actions
    assert ("outbox_failed", "message-1", "provider offline") in state.actions
    assert not any(action[0] == "outbox_released" for action in state.actions)


@pytest.mark.asyncio
async def test_retryable_provider_runtime_failure_is_terminal_for_execution_but_keeps_runner_ready() -> None:
    state = State()
    health = FakeHealthReporter()
    runtime = FakeRuntime(
        error=LLMProviderError(
            provider="deepseek",
            model="deepseek-flash",
            message="rate limited",
            retryable=True,
            status_code=429,
        )
    )
    consumer = _consumer(state, FakeRuntimeFactory(runtime=runtime), health)

    await consumer._handle_message(_message())

    assert state.execution.status == "failed"
    assert state.outbox.status == "failed"
    assert health.unavailable == []
    assert not any(action[0] == "outbox_released" for action in state.actions)


@pytest.mark.asyncio
async def test_non_retryable_provider_failure_marks_runner_unavailable_and_execution_terminal() -> None:
    state = State()
    health = FakeHealthReporter()
    runtime = FakeRuntime(
        error=LLMProviderError(
            provider="deepseek",
            model="deepseek-flash",
            message="invalid API key",
            retryable=False,
            status_code=401,
        )
    )
    consumer = _consumer(state, FakeRuntimeFactory(runtime=runtime), health)

    await consumer._handle_message(_message())

    assert state.execution.status == "failed"
    assert state.outbox.status == "failed"
    assert health.unavailable == [
        {
            "provider": "deepseek",
            "model": "deepseek-flash",
            "error": "invalid API key",
        }
    ]
    assert not any(action[0] == "outbox_released" for action in state.actions)


@pytest.mark.asyncio
async def test_success_marks_execution_completed_and_outbox_processed() -> None:
    state = State()
    health = FakeHealthReporter()
    runtime = FakeRuntime(
        result=SimpleNamespace(answer="resposta", result={"ok": True})
    )
    consumer = _consumer(state, FakeRuntimeFactory(runtime=runtime), health)

    await consumer._handle_message(_message())

    assert state.execution.status == "completed"
    assert state.execution.answer == "resposta"
    assert state.outbox.status == "processed"
    assert health.unavailable == []
