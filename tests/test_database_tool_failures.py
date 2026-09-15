import sqlite3
from pathlib import Path

import pytest

import package.agent.tools.database.executor as executor_module
from package.agent.tools.database.config import UserDatabaseConfig
from package.agent.tools.database.executor import QueryTimeoutError, SQLiteQueryExecutor


def _config(
    path: Path,
    *,
    query_timeout_seconds: float = 5.0,
    max_rows: int = 1_000,
    progress_handler_steps: int = 1_000,
) -> UserDatabaseConfig:
    return UserDatabaseConfig(
        path=path,
        connection_timeout_seconds=5.0,
        query_timeout_seconds=query_timeout_seconds,
        max_rows=max_rows,
        progress_handler_steps=progress_handler_steps,
    )


def _build_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE clientes (id INTEGER PRIMARY KEY, estado TEXT)")
    connection.executemany(
        "INSERT INTO clientes (estado) VALUES (?)",
        [("SC",), ("SP",), ("PR",), ("RS",)],
    )
    connection.commit()
    connection.close()


def test_missing_database_file_fails_in_read_only_mode(tmp_path: Path) -> None:
    executor = SQLiteQueryExecutor(_config(tmp_path / "missing.db"))

    with pytest.raises(sqlite3.OperationalError):
        executor.execute("SELECT 1")


def test_invalid_sql_schema_error_is_propagated_for_agent_self_correction(tmp_path: Path) -> None:
    path = tmp_path / "data.db"
    _build_db(path)
    executor = SQLiteQueryExecutor(_config(path))

    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        executor.execute("SELECT * FROM tabela_inexistente")


def test_invalid_column_error_is_propagated_for_agent_self_correction(tmp_path: Path) -> None:
    path = tmp_path / "data.db"
    _build_db(path)
    executor = SQLiteQueryExecutor(_config(path))

    with pytest.raises(sqlite3.OperationalError, match="no such column"):
        executor.execute("SELECT coluna_inexistente FROM clientes")


def test_query_result_is_truncated_at_configured_row_limit(tmp_path: Path) -> None:
    path = tmp_path / "data.db"
    _build_db(path)
    executor = SQLiteQueryExecutor(_config(path, max_rows=2))

    result = executor.execute("SELECT id, estado FROM clientes ORDER BY id")

    assert len(result.rows) == 2
    assert result.truncated is True
    assert result.columns == ("id", "estado")


def test_query_timeout_is_normalized_to_query_timeout_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "data.db"
    _build_db(path)
    executor = SQLiteQueryExecutor(
        _config(
            path,
            query_timeout_seconds=1.0,
            progress_handler_steps=1,
        )
    )
    calls = 0

    def monotonic() -> float:
        nonlocal calls
        calls += 1
        return 0.0 if calls == 1 else 2.0

    monkeypatch.setattr(executor_module.time, "monotonic", monotonic)

    with pytest.raises(QueryTimeoutError, match="configured timeout"):
        executor.execute(
            "WITH RECURSIVE cnt(x) AS ("
            "SELECT 1 UNION ALL SELECT x + 1 FROM cnt WHERE x < 1000000"
            ") SELECT SUM(x) FROM cnt"
        )
