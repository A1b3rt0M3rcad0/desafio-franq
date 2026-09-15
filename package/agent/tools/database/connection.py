import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def _sqlite_read_only_uri(path: Path) -> str:
    resolved = path.expanduser().resolve()
    return f"file:{resolved.as_posix()}?mode=ro"


@contextmanager
def open_read_only_connection(path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(_sqlite_read_only_uri(path), uri=True)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()
