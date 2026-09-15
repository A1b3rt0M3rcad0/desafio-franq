from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    agent_database_url: str
    redis_url: str
    execution_hot_state_ttl_seconds: int
