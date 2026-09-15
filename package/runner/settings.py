from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class RunnerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    agent_database_url: str
    redis_url: str
    user_database_path: Path
    runner_id: str
    outbox_poll_interval_seconds: float
    outbox_batch_size: int
    execution_hot_state_ttl_seconds: int
