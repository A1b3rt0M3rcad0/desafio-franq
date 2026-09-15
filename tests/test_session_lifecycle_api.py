from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from package.api.http.routes import sessions as sessions_route
from package.api.http.schemas.session import StartSessionRequest, UpdateSessionRequest


class FakeDatabaseSession:
    def __init__(self) -> None:
        self.committed = False
        self.refreshed: list[object] = []

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, entity: object) -> None:
        self.refreshed.append(entity)


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
async def test_start_session_persists_session_execution_and_outbox_in_one_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = FakeSessionFactory()
    session = SimpleNamespace(id="session-1", title="Pergunta inicial")
    execution = SimpleNamespace(id="execution-1")
    created: list[tuple[dict[str, object], str | None]] = []
    enqueued: list[dict[str, object]] = []

    class FakeSessionRepository:
        def __init__(self, db) -> None:
            assert db is factory.db

        async def create(self, metadata, *, title=None):
            created.append((metadata, title))
            return session

    class FakeExecutionRepository:
        def __init__(self, db) -> None:
            assert db is factory.db

        async def create(self, session_id: str, question: str):
            assert (session_id, question) == ("session-1", "Pergunta inicial")
            return execution

    class FakeOutboxRepository:
        def __init__(self, db) -> None:
            assert db is factory.db

        async def enqueue(self, **kwargs):
            enqueued.append(kwargs)
            return object()

    monkeypatch.setattr(sessions_route, "SessionRepository", FakeSessionRepository)
    monkeypatch.setattr(sessions_route, "ExecutionRepository", FakeExecutionRepository)
    monkeypatch.setattr(sessions_route, "OutboxRepository", FakeOutboxRepository)
    monkeypatch.setattr(sessions_route, "build_session_title", lambda value: value)
    monkeypatch.setattr(sessions_route, "present_session", lambda value: {"id": value.id})
    monkeypatch.setattr(sessions_route, "present_execution", lambda value: {"id": value.id})
    monkeypatch.setattr(
        sessions_route,
        "StartedSessionResponse",
        lambda **kwargs: kwargs,
    )

    response = await sessions_route.start_session(
        StartSessionRequest(question="Pergunta inicial", metadata={"client": "test"}),
        session_factory=factory,
    )

    assert response == {
        "session": {"id": "session-1"},
        "execution": {"id": "execution-1"},
    }
    assert created == [({"client": "test"}, "Pergunta inicial")]
    assert factory.db.committed is True
    assert factory.db.refreshed == [session, execution]
    assert enqueued == [
        {
            "event_type": "execution.requested",
            "aggregate_id": "execution-1",
            "payload": {
                "execution_id": "execution-1",
                "session_id": "session-1",
                "question": "Pergunta inicial",
            },
        }
    ]


@pytest.mark.asyncio
async def test_update_session_changes_title(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = FakeSessionFactory()
    entity = SimpleNamespace(id="session-1", title="Antigo")

    class FakeSessionRepository:
        def __init__(self, db) -> None:
            assert db is factory.db

        async def get(self, session_id: str):
            return entity if session_id == "session-1" else None

        async def update_title(self, target, title: str):
            assert target is entity
            target.title = title
            return target

    monkeypatch.setattr(sessions_route, "SessionRepository", FakeSessionRepository)
    monkeypatch.setattr(sessions_route, "present_session", lambda value: {"title": value.title})

    response = await sessions_route.update_session(
        "session-1",
        UpdateSessionRequest(title="Novo título"),
        session_factory=factory,
    )

    assert response == {"title": "Novo título"}
    assert factory.db.committed is True


@pytest.mark.asyncio
async def test_delete_session_rejects_active_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = FakeSessionFactory()

    class FakeSessionRepository:
        def __init__(self, db) -> None:
            assert db is factory.db

        async def get(self, session_id: str):
            return object()

        async def has_active_executions(self, session_id: str) -> bool:
            return True

    monkeypatch.setattr(sessions_route, "SessionRepository", FakeSessionRepository)

    with pytest.raises(HTTPException) as exc_info:
        await sessions_route.delete_session("session-1", session_factory=factory)

    assert exc_info.value.status_code == 409
    assert factory.db.committed is False
