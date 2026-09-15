from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def create_agent_database_engine(database_url: str) -> AsyncEngine:
    """Create the internal/durable agent database engine.

    This engine is never used to connect to the user's analytical database.
    """
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        future=True,
    )
