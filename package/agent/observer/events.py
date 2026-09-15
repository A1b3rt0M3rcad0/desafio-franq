from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ExecutionEventType(StrEnum):
    EXECUTION_STARTED = "execution.started"
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED = "execution.failed"
    AGENT_ITERATION_STARTED = "agent.iteration.started"
    AGENT_DECISION = "agent.decision"
    AGENT_MAX_ITERATIONS_REACHED = "agent.max_iterations_reached"
    ANSWER_GENERATED = "answer.generated"
    CONTEXT_LOADED = "context.loaded"
    SCHEMA_INSPECTED = "schema.inspected"
    PLAN_CREATED = "plan.created"
    LLM_STARTED = "llm.started"
    ASSISTANT_DELTA = "assistant.delta"
    LLM_COMPLETED = "llm.completed"
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    SQL_GENERATED = "sql.generated"
    SQL_EXECUTED = "sql.executed"
    VISUALIZATION_SELECTED = "visualization.selected"


TRACEABLE_EVENT_TYPES = {
    ExecutionEventType.EXECUTION_STARTED,
    ExecutionEventType.EXECUTION_COMPLETED,
    ExecutionEventType.EXECUTION_FAILED,
    ExecutionEventType.AGENT_ITERATION_STARTED,
    ExecutionEventType.AGENT_DECISION,
    ExecutionEventType.AGENT_MAX_ITERATIONS_REACHED,
    ExecutionEventType.ANSWER_GENERATED,
    ExecutionEventType.CONTEXT_LOADED,
    ExecutionEventType.SCHEMA_INSPECTED,
    ExecutionEventType.PLAN_CREATED,
    ExecutionEventType.TOOL_STARTED,
    ExecutionEventType.TOOL_COMPLETED,
    ExecutionEventType.TOOL_FAILED,
    ExecutionEventType.SQL_GENERATED,
    ExecutionEventType.SQL_EXECUTED,
    ExecutionEventType.VISUALIZATION_SELECTED,
}


class ExecutionEvent(BaseModel):
    execution_id: str
    type: ExecutionEventType
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
