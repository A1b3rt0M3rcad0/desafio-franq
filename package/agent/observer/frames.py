from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


EXECUTION_STATE_FRAME = "execution.state"
REALTIME_UNAVAILABLE_FRAME = "execution.realtime_unavailable"
HEARTBEAT_FRAME = "heartbeat"
TERMINAL_EXECUTION_STATUSES = {"completed", "failed"}
TERMINAL_EVENT_TYPES = {"execution.completed", "execution.failed"}


class ExecutionFrame(BaseModel):
    execution_id: str
    type: str
    sequence: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
