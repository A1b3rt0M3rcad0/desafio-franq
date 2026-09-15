from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from package.agent.llm.config import LLMProvider, ReasoningEffort


class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class OpenAIProviderSettings(EnvSettings):
    openai_api_key: SecretStr
    openai_base_url: str
    openai_model: str
    openai_timeout_seconds: float
    openai_max_output_tokens: int
    openai_max_retries: int
    openai_reasoning_effort: ReasoningEffort
    openai_store: bool


class DeepSeekProviderSettings(EnvSettings):
    deepseek_api_key: SecretStr
    deepseek_base_url: str
    deepseek_model: str
    deepseek_timeout_seconds: float
    deepseek_max_output_tokens: int
    deepseek_max_retries: int
    deepseek_reasoning_effort: ReasoningEffort


class RunnerSettings(EnvSettings):
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

    agent_runtime_max_iterations: int
    agent_runtime_max_sql_retries: int
    agent_tool_max_concurrency_per_tool: int

    agent_context_budget_percent: float
    agent_context_summary_fallback_max_messages: int
    agent_context_summary_fallback_max_chars_per_message: int
    agent_context_retriever_default_limit: int
    agent_context_retriever_max_limit: int

    observer_projection_max_activities: int

    runner_id: str
    runner_health_ttl_seconds: int = 15
    runner_health_heartbeat_seconds: float = 5.0
    outbox_poll_interval_seconds: float
    outbox_batch_size: int
    outbox_max_attempts: int = 3
    outbox_retry_base_delay_seconds: float
    outbox_retry_max_delay_seconds: float
    outbox_retry_exponent_cap: int
