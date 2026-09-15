from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from package.agent.database.config.connection import create_session_factory
from package.agent.database.config.engine import create_agent_database_engine


def compose_agent_database(
    database_url: str,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_agent_database_engine(database_url)
    return engine, create_session_factory(engine)
