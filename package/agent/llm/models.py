from enum import StrEnum

from pydantic import BaseModel


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class LLMMessage(BaseModel):
    role: MessageRole
    content: str


class LLMChunk(BaseModel):
    content: str
