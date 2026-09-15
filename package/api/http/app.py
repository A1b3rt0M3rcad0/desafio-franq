from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from package.agent.database.models import Base
from package.api.http.dependencies import get_engine, get_redis
from package.api.http.routes.events import router as events_router
from package.api.http.routes.executions import router as executions_router
from package.api.http.routes.sessions import router as sessions_router
from package.api.http.routes.trace import router as trace_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    engine = get_engine()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield
    await get_redis().aclose()
    await engine.dispose()


app = FastAPI(title="Franq Data Assistant", lifespan=lifespan)
app.include_router(sessions_router)
app.include_router(executions_router)
app.include_router(events_router)
app.include_router(trace_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
