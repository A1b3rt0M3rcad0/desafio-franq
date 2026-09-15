from typing import Any

from pydantic import BaseModel, Field


class ConversationTurn(BaseModel):
    role: str
    content: str


class AgentContext(BaseModel):
    session_id: str
    execution_id: str
    question: str
    history: list[ConversationTurn] = Field(default_factory=list)
    schema: list[dict[str, Any]] | None = None
