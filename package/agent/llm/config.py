from dataclasses import dataclass
from enum import StrEnum


class LLMProvider(StrEnum):
    OPENAI_RESPONSES = "openai_responses"
    GPT_CHAT = "gpt_chat"


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
    reasoning_effort: ReasoningEffort
    store: bool
