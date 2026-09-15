from enum import StrEnum

from pydantic import BaseModel


class MessageRole(StrEnum):
    DEVELOPER = "developer"
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class LLMMessage(BaseModel):
    role: MessageRole
    content: str
    tool_call_id: str | None = None


class LLMChunk(BaseModel):
    content: str
