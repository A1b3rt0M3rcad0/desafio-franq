from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from package.api.http.schemas.execution import ExecutionResponse


class CreateSessionRequest(BaseModel):
    metadata: dict[str, Any] = Field(default_factory=dict)


class StartSessionRequest(BaseModel):
    question: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("question cannot be empty")
        return normalized


class UpdateSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        normalized = " ".join(value.split()).strip()
        if not normalized:
            raise ValueError("title cannot be empty")
        return normalized


class SessionResponse(BaseModel):
    id: str
    title: str | None = None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class StartedSessionResponse(BaseModel):
    session: SessionResponse
    execution: ExecutionResponse
