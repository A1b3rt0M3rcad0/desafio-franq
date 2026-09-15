from pathlib import Path

from package.agent.tools.database.config import UserDatabaseConfig
from package.agent.tools.database.executor import SQLiteQueryExecutor
from package.agent.tools.database.inspector import SQLiteSchemaInspector
from package.agent.tools.database.tool import DatabaseTool


def compose_user_database_tool(
    *,
    path: Path,
    connection_timeout_seconds: float,
    query_timeout_seconds: float,
    max_rows: int,
    progress_handler_steps: int,
) -> DatabaseTool:
    """Compose the user/business database tool.

    This connection is intentionally separate from the internal agent/session database.
    """
    config = UserDatabaseConfig(
        path=path,
        connection_timeout_seconds=connection_timeout_seconds,
        query_timeout_seconds=query_timeout_seconds,
        max_rows=max_rows,
        progress_handler_steps=progress_handler_steps,
    )
    return DatabaseTool(
        inspector=SQLiteSchemaInspector(config),
        executor=SQLiteQueryExecutor(config),
    )
