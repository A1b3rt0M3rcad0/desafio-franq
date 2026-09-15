from redis.asyncio import Redis

from package.agent.cache.connection import create_redis_connection
from package.agent.cache.event_stream import ExecutionEventStream
from package.agent.cache.execution_state import ExecutionHotState


def compose_redis(
    *,
    redis_url: str,
    key_prefix: str,
    ttl_seconds: int,
    stream_maxlen: int,
    stream_read_block_ms: int,
    stream_read_count: int,
) -> tuple[Redis, ExecutionHotState, ExecutionEventStream]:
    redis = create_redis_connection(redis_url)
    hot_state = ExecutionHotState(
        redis,
        key_prefix=key_prefix,
        ttl_seconds=ttl_seconds,
    )
    event_stream = ExecutionEventStream(
        redis,
        key_prefix=key_prefix,
        maxlen=stream_maxlen,
        ttl_seconds=ttl_seconds,
        read_block_ms=stream_read_block_ms,
        read_count=stream_read_count,
    )
    return redis, hot_state, event_stream
