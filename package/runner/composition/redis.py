from redis.asyncio import Redis

from package.agent.cache.connection import create_redis_connection
from package.agent.cache.event_stream import ExecutionEventStream
from package.agent.cache.execution_state import ExecutionHotState


def compose_redis(
    *,
    redis_url: str,
    ttl_seconds: int,
) -> tuple[Redis, ExecutionHotState, ExecutionEventStream]:
    redis = create_redis_connection(redis_url)
    hot_state = ExecutionHotState(redis, ttl_seconds=ttl_seconds)
    event_stream = ExecutionEventStream(redis, ttl_seconds=ttl_seconds)
    return redis, hot_state, event_stream
