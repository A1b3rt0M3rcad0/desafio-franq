from dataclasses import dataclass
from enum import StrEnum


class LLMProvider(StrEnum):
    OPENAI = "openai"
    DEEPSEEK = "deepseek"


class ReasoningEffort(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


@dataclass(frozen=True, slots=True)
class OpenAIConfig:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float
    max_output_tokens: int
    max_retries: int
    reasoning_effort: ReasoningEffort
    store: bool


@dataclass(frozen=True, slots=True)
class DeepSeekConfig:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float
    max_output_tokens: int
    max_retries: int
    reasoning_effort: ReasoningEffort
