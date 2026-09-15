from typing import Any

from pydantic import BaseModel, Field


class RuntimeState(BaseModel):
    execution_id: str
    session_id: str
    question: str
    answer: str = ""
    step: str = "created"
    metadata: dict[str, Any] = Field(default_factory=dict)
