from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionResponse(BaseModel):
    id: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
