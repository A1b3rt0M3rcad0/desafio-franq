from typing import Any

from pydantic import BaseModel, Field


class ConversationTurn(BaseModel):
    role: str
    content: str


class SkillDescriptor(BaseModel):
    name: str
    description: str


class ToolDescriptor(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class AgentContext(BaseModel):
    session_id: str
    execution_id: str
    question: str
    history: list[ConversationTurn] = Field(default_factory=list)
    skills: list[SkillDescriptor] = Field(default_factory=list)
    tools: list[ToolDescriptor] = Field(default_factory=list)
    schema: list[dict[str, Any]] | None = None
