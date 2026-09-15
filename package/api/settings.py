from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    agent_database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/desafio_franq"
    redis_url: str = "redis://localhost:6379/0"
    execution_hot_state_ttl_seconds: int = 21_600
