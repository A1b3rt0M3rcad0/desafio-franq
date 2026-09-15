from package.agent.database.models.trace import ExecutionTrace
from package.agent.trace.models import TraceStep


def present_trace(trace: ExecutionTrace) -> TraceStep:
    return TraceStep(
        sequence=trace.sequence,
        event_type=trace.event_type,
        payload=trace.payload,
        created_at=trace.created_at,
    )
