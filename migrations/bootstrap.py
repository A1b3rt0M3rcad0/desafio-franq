import asyncio
import os
from dataclasses import dataclass
from enum import StrEnum

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from package.agent.database.models import Base


INITIAL_REVISION = "0001_initial_schema"


class SchemaState(StrEnum):
    EMPTY = "empty"
    VERSIONED = "versioned"
    LEGACY_COMPATIBLE = "legacy_compatible"
    LEGACY_INCOMPATIBLE = "legacy_incompatible"


@dataclass(frozen=True, slots=True)
class SchemaInspection:
    state: SchemaState
    missing_tables: tuple[str, ...] = ()
    missing_columns: tuple[str, ...] = ()


def classify_schema(
    actual: dict[str, set[str]],
    expected: dict[str, set[str]],
) -> SchemaInspection:
    if "alembic_version" in actual:
        return SchemaInspection(SchemaState.VERSIONED)

    expected_names = set(expected)
    present_expected = expected_names.intersection(actual)
    if not present_expected:
        return SchemaInspection(SchemaState.EMPTY)

    missing_tables = tuple(sorted(expected_names.difference(actual)))
    missing_columns: list[str] = []
    for table_name in sorted(expected_names.intersection(actual)):
        for column_name in sorted(expected[table_name].difference(actual[table_name])):
            missing_columns.append(f"{table_name}.{column_name}")

    if missing_tables or missing_columns:
        return SchemaInspection(
            SchemaState.LEGACY_INCOMPATIBLE,
            missing_tables=missing_tables,
            missing_columns=tuple(missing_columns),
        )
    return SchemaInspection(SchemaState.LEGACY_COMPATIBLE)


async def inspect_database(database_url: str) -> dict[str, set[str]]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(_inspect_sync)
    finally:
        await engine.dispose()


def _inspect_sync(connection) -> dict[str, set[str]]:
    inspector = inspect(connection)
    return {
        table_name: {column["name"] for column in inspector.get_columns(table_name)}
        for table_name in inspector.get_table_names()
    }


def expected_schema() -> dict[str, set[str]]:
    return {
        table_name: set(table.columns.keys())
        for table_name, table in Base.metadata.tables.items()
    }


def main() -> None:
    load_dotenv()
    database_url = os.environ.get("AGENT_DATABASE_URL")
    if not database_url:
        raise RuntimeError("AGENT_DATABASE_URL is required to bootstrap migrations")

    actual = asyncio.run(inspect_database(database_url))
    inspection = classify_schema(actual, expected_schema())
    config = Config("alembic.ini")

    if inspection.state == SchemaState.LEGACY_INCOMPATIBLE:
        details: list[str] = []
        if inspection.missing_tables:
            details.append(f"missing tables: {', '.join(inspection.missing_tables)}")
        if inspection.missing_columns:
            details.append(f"missing columns: {', '.join(inspection.missing_columns)}")
        raise RuntimeError(
            "Existing database schema is partially compatible but cannot be safely adopted; "
            + "; ".join(details)
        )

    if inspection.state == SchemaState.LEGACY_COMPATIBLE:
        command.stamp(config, INITIAL_REVISION)

    command.upgrade(config, "head")


if __name__ == "__main__":
    main()
