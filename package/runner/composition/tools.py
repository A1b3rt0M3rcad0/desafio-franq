from pathlib import Path

from package.agent.tools.database.config import UserDatabaseConfig
from package.agent.tools.database.executor import SQLiteQueryExecutor
from package.agent.tools.database.inspector import SQLiteSchemaInspector
from package.agent.tools.database.tool import DatabaseTool


def compose_user_database_tool(path: Path) -> DatabaseTool:
    """Compose the user/business database tool.

    This connection is intentionally separate from the internal agent/session database.
    """
    config = UserDatabaseConfig(path=path)
    return DatabaseTool(
        inspector=SQLiteSchemaInspector(config),
        executor=SQLiteQueryExecutor(config),
    )
