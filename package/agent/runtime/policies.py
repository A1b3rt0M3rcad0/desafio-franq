from package.agent.runtime.loop import RuntimePolicy


def create_runtime_policy(*, max_iterations: int, max_sql_retries: int) -> RuntimePolicy:
    if max_iterations < 1:
        raise ValueError("max_iterations must be greater than zero")
    if max_sql_retries < 0:
        raise ValueError("max_sql_retries cannot be negative")
    return RuntimePolicy(
        max_iterations=max_iterations,
        max_sql_retries=max_sql_retries,
    )
