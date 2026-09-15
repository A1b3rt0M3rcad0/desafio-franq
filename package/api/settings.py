from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_title: str
    api_auto_create_schema: bool

    agent_database_url: str

    redis_url: str
    redis_key_prefix: str
    execution_hot_state_ttl_seconds: int
    redis_stream_maxlen: int
    redis_stream_read_block_ms: int
    redis_stream_read_count: int

    runner_health_ttl_seconds: int = 15

    observer_acceptance_poll_seconds: float
    observer_projection_max_activities: int
