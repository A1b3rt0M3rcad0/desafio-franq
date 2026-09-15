from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class UserDatabaseConfig:
    path: Path
    connection_timeout_seconds: float
    query_timeout_seconds: float
    max_rows: int
    progress_handler_steps: int
