from datetime import datetime
from typing import Any

from pydantic import BaseModel


class TraceStep(BaseModel):
    sequence: int
    event_type: str
    payload: dict[str, Any]
    created_at: datetime
