from types import SimpleNamespace

import pytest

from package.api.http.routes import sessions as sessions_route


class FakeDatabaseSession:
    pass


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
async def test_list_sessions_uses_repository_limit_and_presents_each_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = FakeSessionFactory()
    entities = [SimpleNamespace(id="session-1"), SimpleNamespace(id="session-2")]
    observed_limits: list[int] = []

    class FakeSessionRepository:
        def __init__(self, db) -> None:
            assert db is factory.db

        async def list_recent(self, *, limit: int):
            observed_limits.append(limit)
            return entities

    monkeypatch.setattr(sessions_route, "SessionRepository", FakeSessionRepository)
    monkeypatch.setattr(
        sessions_route,
        "present_session",
        lambda entity: {"id": entity.id},
    )

    result = await sessions_route.list_sessions(
        limit=25,
        session_factory=factory,
    )

    assert observed_limits == [25]
    assert result == [{"id": "session-1"}, {"id": "session-2"}]
