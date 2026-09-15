from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class MessageRole(StrEnum):
    DEVELOPER = "developer"
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class LLMModelProfile(BaseModel):
    provider: str
    model: str
    context_window_tokens: int = Field(gt=0)


class LLMToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class LLMToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class LLMMessage(BaseModel):
    role: MessageRole
    content: str
    tool_call_id: str | None = None
    tool_calls: tuple[LLMToolCall, ...] = ()


class LLMChunk(BaseModel):
    content: str


class LLMResponse(BaseModel):
    content: str = ""
    tool_calls: tuple[LLMToolCall, ...] = ()
