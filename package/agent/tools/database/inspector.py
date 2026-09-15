from dataclasses import dataclass

from package.agent.tools.database.config import UserDatabaseConfig
from package.agent.tools.database.connection import open_read_only_connection


@dataclass(frozen=True, slots=True)
class ColumnSchema:
    name: str
    data_type: str
    nullable: bool
    primary_key: bool


@dataclass(frozen=True, slots=True)
class TableSchema:
    name: str
    columns: tuple[ColumnSchema, ...]


class SQLiteSchemaInspector:
    def __init__(self, config: UserDatabaseConfig) -> None:
        self._config = config

    def inspect(self) -> tuple[TableSchema, ...]:
        with open_read_only_connection(self._config) as connection:
            table_rows = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()

            tables: list[TableSchema] = []
            for table_row in table_rows:
                table_name = str(table_row["name"])
                escaped = table_name.replace("'", "''")
                columns = connection.execute(f"PRAGMA table_info('{escaped}')").fetchall()
                tables.append(
                    TableSchema(
                        name=table_name,
                        columns=tuple(
                            ColumnSchema(
                                name=str(column["name"]),
                                data_type=str(column["type"]),
                                nullable=not bool(column["notnull"]),
                                primary_key=bool(column["pk"]),
                            )
                            for column in columns
                        ),
                    )
                )
            return tuple(tables)
