import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from package.agent.tools.database.config import UserDatabaseConfig


def _sqlite_read_only_uri(path: Path) -> str:
    resolved = path.expanduser().resolve()
    return f"file:{resolved.as_posix()}?mode=ro"


@contextmanager
def open_read_only_connection(config: UserDatabaseConfig) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(
        _sqlite_read_only_uri(config.path),
        uri=True,
        timeout=config.connection_timeout_seconds,
    )
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()
