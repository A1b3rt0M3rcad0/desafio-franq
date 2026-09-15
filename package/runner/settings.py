from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from package.agent.llm.config import LLMProvider, ReasoningEffort


class RunnerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    agent_database_url: str

    redis_url: str
    redis_key_prefix: str
    execution_hot_state_ttl_seconds: int
    redis_stream_maxlen: int
    redis_stream_read_block_ms: int
    redis_stream_read_count: int

    user_database_path: Path
    user_database_connection_timeout_seconds: float
    user_database_query_timeout_seconds: float
    user_database_max_rows: int
    user_database_progress_handler_steps: int

    llm_provider: LLMProvider
    openai_api_key: SecretStr
    openai_base_url: str
    openai_model: str
    openai_timeout_seconds: float
    openai_max_output_tokens: int
    openai_reasoning_effort: ReasoningEffort
    openai_store: bool

    agent_runtime_max_iterations: int
    agent_runtime_max_sql_retries: int

    runner_id: str
    outbox_poll_interval_seconds: float
    outbox_batch_size: int
    outbox_retry_base_delay_seconds: float
    outbox_retry_max_delay_seconds: float
    outbox_retry_exponent_cap: int
