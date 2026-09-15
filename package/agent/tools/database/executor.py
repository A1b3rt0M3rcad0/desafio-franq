import time
from dataclasses import dataclass
from typing import Any

from package.agent.tools.database.config import UserDatabaseConfig
from package.agent.tools.database.connection import open_read_only_connection
from package.agent.tools.database.safety import validate_read_only_sql


@dataclass(frozen=True, slots=True)
class QueryResult:
    columns: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]
    truncated: bool


class QueryTimeoutError(TimeoutError):
    pass


class SQLiteQueryExecutor:
    def __init__(self, config: UserDatabaseConfig) -> None:
        self._config = config

    def execute(self, sql: str) -> QueryResult:
        safe_sql = validate_read_only_sql(sql)
        deadline = time.monotonic() + self._config.query_timeout_seconds

        with open_read_only_connection(self._config) as connection:
            def progress_handler() -> int:
                return int(time.monotonic() >= deadline)

            connection.set_progress_handler(
                progress_handler,
                self._config.progress_handler_steps,
            )
            try:
                cursor = connection.execute(safe_sql)
                raw_rows = cursor.fetchmany(self._config.max_rows + 1)
            except Exception as exc:
                if time.monotonic() >= deadline:
                    raise QueryTimeoutError("SQLite query exceeded the configured timeout") from exc
                raise
            finally:
                connection.set_progress_handler(None, 0)

            truncated = len(raw_rows) > self._config.max_rows
            selected_rows = raw_rows[: self._config.max_rows]
            columns = tuple(description[0] for description in (cursor.description or ()))
            rows = tuple(dict(row) for row in selected_rows)
            return QueryResult(columns=columns, rows=rows, truncated=truncated)
