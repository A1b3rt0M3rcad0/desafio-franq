from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class UserDatabaseConfig:
    path: Path
    query_timeout_seconds: float = 5.0
    max_rows: int = 1_000
