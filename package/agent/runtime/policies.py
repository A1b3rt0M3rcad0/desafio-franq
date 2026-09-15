from package.agent.runtime.loop import RuntimePolicy


def create_runtime_policy(
    *,
    max_iterations: int,
    max_sql_retries: int,
    max_parallel_tool_calls_per_tool: int,
) -> RuntimePolicy:
    if max_iterations < 1:
        raise ValueError("max_iterations must be greater than zero")
    if max_sql_retries < 0:
        raise ValueError("max_sql_retries cannot be negative")
    if max_parallel_tool_calls_per_tool < 1:
        raise ValueError("max_parallel_tool_calls_per_tool must be greater than zero")
    return RuntimePolicy(
        max_iterations=max_iterations,
        max_sql_retries=max_sql_retries,
        max_parallel_tool_calls_per_tool=max_parallel_tool_calls_per_tool,
    )
