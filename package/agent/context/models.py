from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SnapshotReason(StrEnum):
    EXECUTION_COMPLETED = "execution_completed"
    BUDGET_COMPACTION = "budget_compaction"


class GlobalContextKind(StrEnum):
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    TOOL_RESULT = "tool_result"
    TOOL_ERROR = "tool_error"


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


class ContextSummary(BaseModel):
    current_request: str
    objective: str | None = None
    established_facts: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    relevant_references: list[str] = Field(default_factory=list)
    continuity_notes: list[str] = Field(default_factory=list)


class ContextSnapshot(BaseModel):
    id: str | None = None
    session_id: str
    execution_id: str
    sequence: int
    reason: SnapshotReason
    summary: ContextSummary
    estimated_tokens: int
    created_at: datetime | None = None


class GlobalContextEntry(BaseModel):
    id: str | None = None
    session_id: str
    execution_id: str
    sequence: int
    kind: GlobalContextKind
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class ContextSearchMatch(BaseModel):
    entry: GlobalContextEntry
    score: float


class ContextBudgetReport(BaseModel):
    model_context_window_tokens: int
    dynamic_budget_tokens: int
    mandatory_tokens: int
    dynamic_tokens: int
    total_estimated_tokens: int
    dynamic_usage_percentage: float
    over_budget: bool


class AgentContext(BaseModel):
    session_id: str
    execution_id: str
    question: str
    history: list[ConversationTurn] = Field(default_factory=list)
    skills: list[SkillDescriptor] = Field(default_factory=list)
    tools: list[ToolDescriptor] = Field(default_factory=list)
    snapshot: ContextSnapshot | None = None
    schema: list[dict[str, Any]] | None = None
