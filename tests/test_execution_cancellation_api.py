from types import SimpleNamespace

import pytest

from package.api.http.routes import executions as executions_route


class FakeDatabaseSession:
    def __init__(self) -> None:
        self.committed = False
        self.refreshed = False

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, execution) -> None:
        del execution
        self.refreshed = True


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
async def test_cancel_endpoint_marks_non_terminal_execution_cancel_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = FakeSessionFactory()
    execution = SimpleNamespace(id="execution-1", status="running")

    class FakeExecutionRepository:
        def __init__(self, db) -> None:
            del db

        async def get(self, execution_id: str):
            assert execution_id == "execution-1"
            return execution

        async def request_cancel(self, value) -> bool:
            assert value is execution
            execution.status = "cancel_requested"
            return True

    monkeypatch.setattr(executions_route, "ExecutionRepository", FakeExecutionRepository)
    monkeypatch.setattr(
        executions_route,
        "present_execution",
        lambda value: {"id": value.id, "status": value.status},
    )

    response = await executions_route.cancel_execution(
        "execution-1",
        session_factory=factory,
    )

    assert response == {"id": "execution-1", "status": "cancel_requested"}
    assert factory.db.committed is True
    assert factory.db.refreshed is True
