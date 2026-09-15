from package.agent.runtime.loop import RuntimePolicy


def create_runtime_policy(*, max_iterations: int, max_sql_retries: int) -> RuntimePolicy:
    return RuntimePolicy(
        max_iterations=max_iterations,
        max_sql_retries=max_sql_retries,
    )
