from functools import lru_cache

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from package.agent.cache.connection import create_redis_connection
from package.agent.cache.event_stream import ExecutionEventStream
from package.agent.cache.execution_state import ExecutionHotState
from package.agent.database.config.connection import create_session_factory
from package.agent.database.config.engine import create_agent_database_engine
from package.api.settings import ApiSettings


@lru_cache
def get_settings() -> ApiSettings:
    return ApiSettings()


@lru_cache
def get_engine() -> AsyncEngine:
    return create_agent_database_engine(get_settings().agent_database_url)


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return create_session_factory(get_engine())


@lru_cache
def get_redis() -> Redis:
    return create_redis_connection(get_settings().redis_url)


def get_event_stream() -> ExecutionEventStream:
    settings = get_settings()
    return ExecutionEventStream(
        get_redis(),
        key_prefix=settings.redis_key_prefix,
        maxlen=settings.redis_stream_maxlen,
        ttl_seconds=settings.execution_hot_state_ttl_seconds,
        read_block_ms=settings.redis_stream_read_block_ms,
        read_count=settings.redis_stream_read_count,
    )


def get_hot_state() -> ExecutionHotState:
    settings = get_settings()
    return ExecutionHotState(
        get_redis(),
        key_prefix=settings.redis_key_prefix,
        ttl_seconds=settings.execution_hot_state_ttl_seconds,
    )
