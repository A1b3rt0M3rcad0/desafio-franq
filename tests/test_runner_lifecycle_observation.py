from types import SimpleNamespace

import pytest

import package.runner.consumers.execution as execution_module
from package.agent.observer.events import ExecutionEventType
from package.runner.consumers.execution import ExecutionConsumer
from package.runner.runtime.retry import OutboxRetryPolicy


class State:
    def __init__(self) -> None:
        self.execution = SimpleNamespace(
            id="execution-1",
            status="pending",
            answer=None,
            result=None,
            error=None,
        )
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
        self.state.actions.append(("commit", self.state.execution.status))

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
        if execution_id == self.state.execution.id:
            return self.state.execution
        return None

    async def mark_running(self, execution) -> None:
        execution.status = "running"
        self.state.actions.append(("execution_running",))

    async def mark_completed(self, execution, *, answer: str, result: dict | None) -> None:
        execution.status = "completed"
        execution.answer = answer
        execution.result = result
        self.state.actions.append(("execution_completed",))

    async def mark_cancelled(self, execution, *, answer=None) -> None:
        execution.status = "cancelled"
        execution.answer = answer
        self.state.actions.append(("execution_cancelled",))

    async def mark_failed(self, execution, error: str) -> None:
        execution.status = "failed"
        execution.error = error
        self.state.actions.append(("execution_failed",))


class FakeOutboxRepository:
    def __init__(self, db: FakeSession) -> None:
        self.state = db.state

    async def mark_processed(self, message) -> None:
        message.status = "processed"
        self.state.actions.append(("outbox_processed",))

    async def mark_failed(self, message, *, error: str) -> None:
        message.status = "failed"
        self.state.actions.append(("outbox_failed", error))


class FakeRuntime:
    async def run(self, *, execution_id: str, session_id: str, question: str):
        del execution_id, session_id, question
        return SimpleNamespace(answer="resposta", result={"rows": 5})


class FakeRuntimeFactory:
    def create(self):
        return FakeRuntime()


class FakeEventSink:
    def __init__(self, state: State) -> None:
        self.state = state

    async def emit(self, event) -> None:
        self.state.actions.append(
            ("event", event.type.value, self.state.execution.status)
        )


class FakeHealthReporter:
    async def mark_unavailable(self, **kwargs) -> None:
        del kwargs


@pytest.fixture(autouse=True)
def _replace_repositories(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(execution_module, "ExecutionRepository", FakeExecutionRepository)
    monkeypatch.setattr(execution_module, "OutboxRepository", FakeOutboxRepository)


@pytest.mark.asyncio
async def test_runner_publishes_terminal_event_only_after_durable_commit() -> None:
    state = State()
    consumer = ExecutionConsumer(
        session_factory=FakeSessionFactory(state),
        runtime_factory=FakeRuntimeFactory(),
        event_sink=FakeEventSink(state),
        runner_id="runner-1",
        batch_size=10,
        max_attempts=3,
        cancellation_poll_seconds=0.001,
        retry_policy=OutboxRetryPolicy(
            base_delay_seconds=2.0,
            max_delay_seconds=60.0,
            exponent_cap=5,
        ),
        health_reporter=FakeHealthReporter(),
    )
    message = SimpleNamespace(
        id="message-1",
        event_type="execution.requested",
        attempts=1,
        payload={
            "execution_id": "execution-1",
            "session_id": "session-1",
            "question": "pergunta",
        },
    )

    await consumer._handle_message(message)

    start_event = (
        "event",
        ExecutionEventType.EXECUTION_STARTED.value,
        "running",
    )
    completed_event = (
        "event",
        ExecutionEventType.EXECUTION_COMPLETED.value,
        "completed",
    )
    assert start_event in state.actions
    assert completed_event in state.actions

    start_index = state.actions.index(start_event)
    completed_index = state.actions.index(completed_event)
    running_commit_index = state.actions.index(("commit", "running"))
    completed_commit_index = state.actions.index(("commit", "completed"))

    assert running_commit_index < start_index
    assert completed_commit_index < completed_index
    assert state.execution.answer == "resposta"
    assert state.outbox.status == "processed"
