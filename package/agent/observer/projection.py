from copy import deepcopy
from typing import Any

from package.agent.observer.events import ExecutionEvent, ExecutionEventType


_PUBLIC_FIELDS: dict[ExecutionEventType, frozenset[str]] = {
    ExecutionEventType.EXECUTION_STARTED: frozenset({"session_id"}),
    ExecutionEventType.EXECUTION_COMPLETED: frozenset({"answer", "result"}),
    ExecutionEventType.EXECUTION_FAILED: frozenset({"error"}),
    ExecutionEventType.AGENT_ITERATION_STARTED: frozenset({"iteration", "max_iterations"}),
    ExecutionEventType.AGENT_DECISION: frozenset({"iteration", "decision", "actions"}),
    ExecutionEventType.AGENT_MAX_ITERATIONS_REACHED: frozenset(
        {"iterations", "max_iterations"}
    ),
    ExecutionEventType.ANSWER_GENERATED: frozenset({"iterations", "stop_reason"}),
    ExecutionEventType.CONTEXT_LOADED: frozenset(
        {"history_turns", "snapshot_sequence", "skills", "tools"}
    ),
    ExecutionEventType.CONTEXT_BUDGET_EXCEEDED: frozenset(
        {"iteration", "dynamic_budget_tokens", "dynamic_tokens_after_compaction"}
    ),
    ExecutionEventType.CONTEXT_SNAPSHOT_CREATED: frozenset(
        {"sequence", "reason", "estimated_tokens"}
    ),
    ExecutionEventType.CONTEXT_RETRIEVED: frozenset({"iteration", "query", "matches"}),
    ExecutionEventType.SKILL_REQUESTED: frozenset(
        {"iteration", "skills", "tool_call_id"}
    ),
    ExecutionEventType.SKILL_CONTEXT_LOADED: frozenset({"iteration", "skills"}),
    ExecutionEventType.SKILL_CONTEXT_RELEASED: frozenset({"iteration", "skills"}),
    ExecutionEventType.SCHEMA_INSPECTED: frozenset({"tables", "table_count"}),
    ExecutionEventType.PLAN_CREATED: frozenset({"steps", "step_count"}),
    ExecutionEventType.LLM_STARTED: frozenset(
        {"iteration", "context_dynamic_tokens", "context_dynamic_budget_tokens"}
    ),
    ExecutionEventType.ASSISTANT_DELTA: frozenset({"content"}),
    ExecutionEventType.LLM_COMPLETED: frozenset(
        {"iteration", "content_length", "tool_call_count"}
    ),
    ExecutionEventType.TOOL_STARTED: frozenset(
        {"iteration", "tool", "tool_call_id", "arguments"}
    ),
    ExecutionEventType.TOOL_COMPLETED: frozenset(
        {"iteration", "tool", "tool_call_id", "result"}
    ),
    ExecutionEventType.TOOL_FAILED: frozenset(
        {"iteration", "tool", "tool_call_id", "error"}
    ),
    ExecutionEventType.SQL_GENERATED: frozenset({"iteration", "sql"}),
    ExecutionEventType.SQL_EXECUTED: frozenset(
        {"iteration", "sql", "row_count", "truncated"}
    ),
    ExecutionEventType.VISUALIZATION_SELECTED: frozenset(
        {"type", "title", "x", "y"}
    ),
}


def public_event(event: ExecutionEvent) -> tuple[str, dict[str, Any]]:
    """Map an internal event to the explicitly allowed public observation payload."""

    allowed = _PUBLIC_FIELDS.get(event.type, frozenset())
    payload = {
        key: deepcopy(value)
        for key, value in event.payload.items()
        if key in allowed
    }
    return event.type.value, payload


def initial_projection(
    execution_id: str,
    durable: dict[str, Any] | None = None,
) -> dict[str, Any]:
    durable = durable or {}
    status = str(durable.get("status") or "pending")
    return {
        "execution_id": execution_id,
        "session_id": durable.get("session_id"),
        "status": status,
        "sequence": 0,
        "stage": _stage_from_status(status),
        "iteration": 0,
        "partial_answer": str(durable.get("answer") or ""),
        "answer": durable.get("answer"),
        "error": durable.get("error"),
        "result": durable.get("result"),
        "active_skills": [],
        "active_tools": [],
        "activities": [],
        "last_event": None,
        "updated_at": _serialize_datetime(durable.get("updated_at")),
    }


def reduce_projection(
    projection: dict[str, Any],
    *,
    event_type: str,
    payload: dict[str, Any],
    sequence: int,
    max_activities: int,
) -> dict[str, Any]:
    """Pure reducer from public runtime facts to the reattachable execution projection."""

    state = deepcopy(projection)
    state["sequence"] = sequence
    state["last_event"] = event_type
    if payload.get("created_at") is not None:
        state["updated_at"] = payload["created_at"]

    if event_type == ExecutionEventType.EXECUTION_STARTED.value:
        state["status"] = "running"
        state["stage"] = "agent"
        state["session_id"] = payload.get("session_id") or state.get("session_id")
    elif event_type == ExecutionEventType.CONTEXT_LOADED.value:
        state["stage"] = "context"
    elif event_type == ExecutionEventType.AGENT_ITERATION_STARTED.value:
        state["stage"] = "agent"
        state["iteration"] = int(payload.get("iteration") or state.get("iteration") or 0)
    elif event_type == ExecutionEventType.LLM_STARTED.value:
        state["stage"] = "reasoning"
    elif event_type == ExecutionEventType.SKILL_REQUESTED.value:
        state["stage"] = "skill"
    elif event_type == ExecutionEventType.SKILL_CONTEXT_LOADED.value:
        state["stage"] = "skill"
        state["active_skills"] = list(payload.get("skills") or [])
    elif event_type == ExecutionEventType.SKILL_CONTEXT_RELEASED.value:
        state["active_skills"] = []
        state["stage"] = "agent"
    elif event_type == ExecutionEventType.TOOL_STARTED.value:
        state["stage"] = "tool"
        _mark_tool_started(state, payload)
    elif event_type in {
        ExecutionEventType.TOOL_COMPLETED.value,
        ExecutionEventType.TOOL_FAILED.value,
    }:
        _mark_tool_finished(state, payload)
        state["stage"] = "agent"
    elif event_type == ExecutionEventType.ANSWER_GENERATED.value:
        state["stage"] = "answer"
    elif event_type == ExecutionEventType.ASSISTANT_DELTA.value:
        content = str(payload.get("content") or "")
        state["partial_answer"] = f"{state.get('partial_answer') or ''}{content}"
        state["stage"] = "answer"
    elif event_type == ExecutionEventType.EXECUTION_COMPLETED.value:
        state["status"] = "completed"
        state["stage"] = "completed"
        state["answer"] = payload.get("answer")
        state["partial_answer"] = str(
            payload.get("answer") or state.get("partial_answer") or ""
        )
        state["result"] = payload.get("result")
        state["active_skills"] = []
        state["active_tools"] = []
    elif event_type == ExecutionEventType.EXECUTION_FAILED.value:
        state["status"] = "failed"
        state["stage"] = "failed"
        state["error"] = payload.get("error")
        state["active_skills"] = []
        state["active_tools"] = []

    if event_type != ExecutionEventType.ASSISTANT_DELTA.value:
        activity_payload = {
            key: deepcopy(value)
            for key, value in payload.items()
            if key != "created_at"
        }
        activities = list(state.get("activities") or [])
        activities.append(
            {
                "sequence": sequence,
                "type": event_type,
                "payload": activity_payload,
                "created_at": payload.get("created_at"),
            }
        )
        state["activities"] = activities[-max_activities:]

    return state


def public_projection(
    projection: dict[str, Any],
    *,
    realtime_available: bool,
) -> dict[str, Any]:
    keys = (
        "execution_id",
        "session_id",
        "status",
        "sequence",
        "stage",
        "iteration",
        "partial_answer",
        "answer",
        "error",
        "result",
        "active_skills",
        "active_tools",
        "activities",
        "last_event",
        "updated_at",
    )
    result = {key: deepcopy(projection.get(key)) for key in keys}
    result["realtime_available"] = realtime_available
    return result


def _mark_tool_started(state: dict[str, Any], payload: dict[str, Any]) -> None:
    call_id = str(payload.get("tool_call_id") or "")
    active = [
        item
        for item in list(state.get("active_tools") or [])
        if str(item.get("tool_call_id") or "") != call_id
    ]
    active.append(
        {
            "tool": payload.get("tool"),
            "tool_call_id": call_id,
            "iteration": payload.get("iteration"),
            "arguments": deepcopy(payload.get("arguments")),
        }
    )
    state["active_tools"] = active


def _mark_tool_finished(state: dict[str, Any], payload: dict[str, Any]) -> None:
    call_id = str(payload.get("tool_call_id") or "")
    state["active_tools"] = [
        item
        for item in list(state.get("active_tools") or [])
        if str(item.get("tool_call_id") or "") != call_id
    ]


def _stage_from_status(status: str) -> str:
    if status == "completed":
        return "completed"
    if status == "failed":
        return "failed"
    if status == "running":
        return "agent"
    return "pending"


def _serialize_datetime(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
