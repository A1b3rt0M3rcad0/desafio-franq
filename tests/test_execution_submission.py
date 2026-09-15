from types import SimpleNamespace

import pytest

from package.api.http.routes import executions as executions_route
from package.api.http.schemas.execution import CreateExecutionRequest


class FakeDatabaseSession:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True


class FakeSessionContext:
    def __init__(self, db: FakeDatabaseSession) -> None:
        self._db = db

    async def __aenter__(self) -> FakeDatabaseSession:
        return self._db

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class FakeSessionFactory:
    def __init__(self) -> None:
        self.db = FakeDatabaseSession()

    def __call__(self) -> FakeSessionContext:
        return FakeSessionContext(self.db)


@pytest.mark.asyncio
async def test_execution_is_persisted_enqueued_and_touches_conversation_recency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = FakeSessionFactory()
    enqueued: list[dict[str, object]] = []
    touched: list[object] = []
    execution = SimpleNamespace(id="execution-1")
    session = object()

    class FakeSessionRepository:
        def __init__(self, db) -> None:
            del db

        async def get(self, session_id: str) -> object:
            assert session_id == "session-1"
            return session

        async def touch(self, entity: object) -> None:
            touched.append(entity)

    class FakeExecutionRepository:
        def __init__(self, db) -> None:
            del db

        async def create(self, session_id: str, question: str):
            assert session_id == "session-1"
            assert question == "Olá"
            return execution

    class FakeOutboxRepository:
        def __init__(self, db) -> None:
            del db

        async def enqueue(self, **payload):
            enqueued.append(payload)
            return object()

    monkeypatch.setattr(executions_route, "SessionRepository", FakeSessionRepository)
    monkeypatch.setattr(executions_route, "ExecutionRepository", FakeExecutionRepository)
    monkeypatch.setattr(executions_route, "OutboxRepository", FakeOutboxRepository)
    monkeypatch.setattr(
        executions_route,
        "present_execution",
        lambda value: {"id": value.id},
    )

    response = await executions_route.create_execution(
        "session-1",
        CreateExecutionRequest(question="Olá"),
        session_factory=factory,
    )

    assert response == {"id": "execution-1"}
    assert factory.db.committed is True
    assert touched == [session]
    assert enqueued == [
        {
            "event_type": "execution.requested",
            "aggregate_id": "execution-1",
            "payload": {
                "execution_id": "execution-1",
                "session_id": "session-1",
                "question": "Olá",
            },
        }
    ]
