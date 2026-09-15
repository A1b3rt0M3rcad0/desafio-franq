from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class RunnerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    agent_database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/desafio_franq"
    redis_url: str = "redis://localhost:6379/0"
    user_database_path: Path = Path("data/anexo_desafio_1.db")
    runner_id: str = "runner-local"
    outbox_poll_interval_seconds: float = 0.5
    outbox_batch_size: int = 10
    execution_hot_state_ttl_seconds: int = 21_600
