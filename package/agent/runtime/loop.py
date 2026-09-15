from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RuntimePolicy:
    max_iterations: int = 8
    max_sql_retries: int = 2
