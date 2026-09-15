import asyncio
from dataclasses import asdict
from typing import Any

from package.agent.tools.database.executor import SQLiteQueryExecutor
from package.agent.tools.database.inspector import SQLiteSchemaInspector


class DatabaseTool:
    name = "database"
    description = "Inspect the user database schema and execute read-only analytical SQL queries."
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["inspect_schema", "query"],
                "description": "Inspect the schema or execute a read-only analytical query.",
            },
            "sql": {
                "type": "string",
                "description": "SQL query. Required when action is query.",
            },
        },
        "required": ["action"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        *,
        inspector: SQLiteSchemaInspector,
        executor: SQLiteQueryExecutor,
    ) -> None:
        self._inspector = inspector
        self._executor = executor

    async def invoke(self, arguments: dict[str, Any]) -> Any:
        action = arguments.get("action")
        if action == "inspect_schema":
            schema = await asyncio.to_thread(self._inspector.inspect)
            return [asdict(table) for table in schema]
        if action == "query":
            sql = str(arguments.get("sql", ""))
            result = await asyncio.to_thread(self._executor.execute, sql)
            return asdict(result)
        raise ValueError(f"Unsupported database action: {action!r}")
