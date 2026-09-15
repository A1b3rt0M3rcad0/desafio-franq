import sqlite3
from pathlib import Path

from package.agent.tools.database.config import UserDatabaseConfig
from package.agent.tools.database.executor import SQLiteQueryExecutor
from package.agent.tools.database.inspector import SQLiteSchemaInspector


def _build_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE clientes (id INTEGER PRIMARY KEY, estado TEXT)")
    connection.execute("INSERT INTO clientes (estado) VALUES ('SC'), ('SP'), ('SC')")
    connection.commit()
    connection.close()


def test_inspects_schema_and_executes_read_only_query(tmp_path: Path) -> None:
    path = tmp_path / "data.db"
    _build_db(path)
    config = UserDatabaseConfig(
        path=path,
        connection_timeout_seconds=5.0,
        query_timeout_seconds=5.0,
        max_rows=1_000,
        progress_handler_steps=1_000,
    )

    schema = SQLiteSchemaInspector(config).inspect()
    result = SQLiteQueryExecutor(config).execute(
        "SELECT estado, COUNT(*) AS total FROM clientes GROUP BY estado ORDER BY total DESC"
    )

    assert schema[0].name == "clientes"
    assert {column.name for column in schema[0].columns} == {"id", "estado"}
    assert result.rows[0] == {"estado": "SC", "total": 2}
