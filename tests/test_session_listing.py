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
async def test_list_sessions_uses_pagination_and_hides_empty_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = FakeSessionFactory()
    entities = [SimpleNamespace(id="session-1"), SimpleNamespace(id="session-2")]
    observed_calls: list[tuple[int, int, bool]] = []

    class FakeSessionRepository:
        def __init__(self, db) -> None:
            assert db is factory.db

        async def list_recent(
            self,
            *,
            limit: int,
            offset: int,
            only_with_executions: bool,
        ):
            observed_calls.append((limit, offset, only_with_executions))
            return entities

    monkeypatch.setattr(sessions_route, "SessionRepository", FakeSessionRepository)
    monkeypatch.setattr(
        sessions_route,
        "present_session",
        lambda entity: {"id": entity.id},
    )

    result = await sessions_route.list_sessions(
        limit=25,
        offset=10,
        session_factory=factory,
    )

    assert observed_calls == [(25, 10, True)]
    assert result == [{"id": "session-1"}, {"id": "session-2"}]
