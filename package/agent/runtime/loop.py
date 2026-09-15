from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RuntimePolicy:
    max_iterations: int
    max_sql_retries: int
