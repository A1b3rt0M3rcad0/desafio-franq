from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CreateExecutionRequest(BaseModel):
    question: str


class ExecutionResponse(BaseModel):
    id: str
    session_id: str
    question: str
    status: str
    answer: str | None
    error: str | None
    result: dict[str, Any] | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
